"""Synthetic demo dataset (no real vacancies, no ESCO files, no API key needed).

Writes into the DEMO data directory only (requires SKILLRADAR_DEMO=1):
  raw/softon/synthetic_jobs.json   - fictional vacancies in the Softon envelope format
  raw/esco/*.csv                   - a small SYNTHETIC taxonomy in the ESCO CSV layout

Everything is invented for demonstration: employers, job boards, texts, salaries and URLs (example.com).
The taxonomy reuses plain English skill/occupation names so the curated aliases and RU/AZ display labels work,
but its URIs are synthetic (example.org) and it is NOT the ESCO dataset. Real analytics require the real
Softon export / API and the official ESCO download (see docs/data_sources.md).
"""
from __future__ import annotations

import csv
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 20261126
URI_SKILL = "https://example.org/skillradar-demo/skill/"
URI_OCC = "https://example.org/skillradar-demo/occupation/"

# skill label -> (skill type, phrases the matcher recognises in az / ru / en text)
SKILLS: dict[str, tuple[str, dict[str, list[str]]]] = {
    "English": ("knowledge", {"az": ["ingilis dili"], "ru": ["английский язык"], "en": ["English"]}),
    "Russian": ("knowledge", {"az": ["rus dili"], "ru": ["русский язык"], "en": ["Russian"]}),
    "Azerbaijani": ("knowledge", {"az": ["Azərbaycan dili"], "ru": ["азербайджанский язык"], "en": ["Azerbaijani"]}),
    "Turkish": ("knowledge", {"az": ["türk dili"], "ru": ["турецкий язык"], "en": ["Turkish"]}),
    "use spreadsheets software": ("skill/competence", {"az": ["Excel"], "ru": ["Excel"], "en": ["Excel"]}),
    "use microsoft office": ("skill/competence", {"az": ["MS Office"], "ru": ["MS Office"], "en": ["MS Office"]}),
    "use presentation software": ("skill/competence", {"az": ["PowerPoint"], "ru": ["PowerPoint"], "en": ["PowerPoint"]}),
    "use word processing software": ("skill/competence", {"az": ["MS Word"], "ru": ["MS Word"], "en": ["MS Word"]}),
    "work in teams": ("skill/competence", {"az": ["komandada işləmək bacarığı"], "ru": ["работа в команде"], "en": ["work in teams"]}),
    "assume responsibility": ("skill/competence", {"az": ["məsuliyyətli olmaq"], "ru": ["ответственность"], "en": ["assume responsibility"]}),
    "communication": ("knowledge", {"az": ["ünsiyyət bacarıqları"], "ru": ["коммуникабельность"], "en": ["communication"]}),
    "sales activities": ("knowledge", {"az": ["satış təcrübəsi"], "ru": ["опыт продаж"], "en": ["sales activities"]}),
    "customer service": ("knowledge", {"az": ["müştəri xidməti"], "ru": ["обслуживание клиентов"], "en": ["customer service"]}),
    "accounting": ("knowledge", {"az": ["mühasibat uçotu"], "ru": ["бухгалтерский учет"], "en": ["accounting"]}),
    "tax legislation": ("knowledge", {"az": ["vergi qanunvericiliyi"], "ru": ["налоговое законодательство"], "en": ["tax legislation"]}),
    "financial statements": ("knowledge", {"az": ["maliyyə hesabatları"], "ru": ["финансовая отчетность"], "en": ["financial statements"]}),
    "International Financial Reporting Standards": ("knowledge", {"az": ["BMHS"], "ru": ["МСФО"], "en": ["IFRS"]}),
    "SAP R3": ("knowledge", {"az": ["SAP"], "ru": ["SAP"], "en": ["SAP"]}),
    "operate cash register": ("skill/competence", {"az": ["kassa aparatı ilə işləmək"], "ru": ["kassa aparatı"], "en": ["operate cash register"]}),
    "perform cleaning duties": ("skill/competence", {"az": ["təmizlik işləri"], "ru": ["уборка помещений"], "en": ["perform cleaning duties"]}),
    "drive vehicles": ("skill/competence", {"az": ["sürücülük vəsiqəsi"], "ru": ["водительские права"], "en": ["drive vehicles"]}),
    "logistics": ("knowledge", {"az": ["logistika"], "ru": ["логистика"], "en": ["logistics"]}),
    "negotiate with stakeholders": ("skill/competence", {"az": ["danışıqlar aparmaq"], "ru": ["danışıqlar aparmaq"], "en": ["negotiate with stakeholders"]}),
    "think analytically": ("skill/competence", {"az": ["analitik düşüncə"], "ru": ["аналитическое мышление"], "en": ["think analytically"]}),
    "statistics": ("knowledge", {"az": ["statistika"], "ru": ["statistika"], "en": ["statistics"]}),
    "SQL": ("knowledge", {"az": ["SQL"], "ru": ["SQL"], "en": ["SQL"]}),
    "JavaScript": ("knowledge", {"az": ["JavaScript"], "ru": ["JavaScript"], "en": ["JavaScript"]}),
    "TypeScript": ("knowledge", {"az": ["TypeScript"], "ru": ["TypeScript"], "en": ["TypeScript"]}),
    "CSS": ("knowledge", {"az": ["CSS"], "ru": ["CSS"], "en": ["CSS"]}),
    "PostgreSQL": ("knowledge", {"az": ["PostgreSQL"], "ru": ["PostgreSQL"], "en": ["PostgreSQL"]}),
    "MySQL": ("knowledge", {"az": ["MySQL"], "ru": ["MySQL"], "en": ["MySQL"]}),
    "Python": ("knowledge", {"az": ["Python"], "ru": ["Python"], "en": ["Python"]}),
    "data analytics": ("knowledge", {"az": ["data analytics"], "ru": ["data analytics"], "en": ["data analytics"]}),
    "machine learning": ("knowledge", {"az": ["machine learning"], "ru": ["machine learning"], "en": ["machine learning"]}),
    "Agile development": ("knowledge", {"az": ["Agile development"], "ru": ["Agile development"], "en": ["Agile development"]}),
    "customer relationship management": ("knowledge", {"az": ["CRM"], "ru": ["CRM"], "en": ["CRM"]}),
    "graphic design": ("knowledge", {"az": ["qrafik dizayn"], "ru": ["qrafik dizayn"], "en": ["graphic design"]}),
    "Adobe Photoshop": ("knowledge", {"az": ["Photoshop"], "ru": ["Photoshop"], "en": ["Photoshop"]}),
    "Adobe Illustrator": ("knowledge", {"az": ["Illustrator"], "ru": ["Illustrator"], "en": ["Illustrator"]}),
    "social media management": ("knowledge", {"az": ["SMM"], "ru": ["SMM"], "en": ["SMM"]}),
    "marketing principles": ("knowledge", {"az": ["marketinq"], "ru": ["маркетинг"], "en": ["marketing principles"]}),
    "digital marketing techniques": ("knowledge", {"az": ["rəqəmsal marketinq"], "ru": ["rəqəmsal marketinq"], "en": ["digital marketing techniques"]}),
    "project management": ("knowledge", {"az": ["layihə idarəetməsi"], "ru": ["управление проектами"], "en": ["project management"]}),
    "manage time": ("skill/competence", {"az": ["vaxtın idarə edilməsi"], "ru": ["vaxtın idarə edilməsi"], "en": ["manage time"]}),
    "recruit employees": ("skill/competence", {"az": ["işə qəbul prosesi"], "ru": ["подбор персонала"], "en": ["recruit employees"]}),
    "human resource management": ("knowledge", {"az": ["insan resursları"], "ru": ["insan resursları"], "en": ["human resource management"]}),
    "have computer literacy": ("skill/competence", {"az": ["kompüter bilikləri"], "ru": ["kompüter bilikləri"], "en": ["have computer literacy"]}),
    "work independently": ("skill/competence", {"az": ["sərbəst işləmək"], "ru": ["самостоятельность"], "en": ["work independently"]}),
    "lead a team": ("skill/competence", {"az": ["komandaya rəhbərlik"], "ru": ["komandaya rəhbərlik"], "en": ["lead a team"]}),
    "first aid": ("knowledge", {"az": ["ilk tibbi yardım"], "ru": ["ilk tibbi yardım"], "en": ["first aid"]}),
    "financial analysis": ("knowledge", {"az": ["maliyyə təhlili"], "ru": ["финансовый анализ"], "en": ["financial analysis"]}),
    "use CAD software": ("skill/competence", {"az": ["AutoCAD"], "ru": ["AutoCAD"], "en": ["AutoCAD"]}),
    "health and safety regulations": ("knowledge", {"az": ["əməyin mühafizəsi"], "ru": ["охрана труда"], "en": ["health and safety regulations"]}),
    # taxonomy-only skills (appear in occupation profiles; not used in vacancy texts)
    "achieve sales targets": ("skill/competence", {}), "sales argumentation": ("knowledge", {}),
    "maintain relationship with customers": ("skill/competence", {}), "set sales goals": ("skill/competence", {}),
    "supervise sales activities": ("skill/competence", {}), "plan marketing campaigns": ("skill/competence", {}),
    "perform market research": ("skill/competence", {}), "manage staff": ("skill/competence", {}),
    "prepare financial statements": ("skill/competence", {}), "calculate tax": ("skill/competence", {}),
    "bookkeeping regulations": ("knowledge", {}), "check accounting records": ("skill/competence", {}),
    "process payments": ("skill/competence", {}), "stock shelves": ("skill/competence", {}),
    "maintain store cleanliness": ("skill/competence", {}), "greet guests": ("skill/competence", {}),
    "provide information": ("skill/competence", {}), "data models": ("knowledge", {}),
    "cope with stress": ("skill/competence", {}), "manage inventory": ("skill/competence", {}),
}

# occupation -> (titles in az/ru/en, core skills (likely in text), essential profile, optional profile, salary floor range)
OCCUPATIONS: dict[str, dict] = {
    "sales manager": {"titles": ["Satış meneceri", "Менеджер по продажам", "Sales Manager"],
                      "core": ["sales activities", "negotiate with stakeholders", "customer relationship management", "English", "Russian", "use microsoft office", "communication", "assume responsibility"],
                      "essential": ["sales activities", "achieve sales targets", "set sales goals", "supervise sales activities", "negotiate with stakeholders", "customer relationship management", "perform market research"],
                      "optional": ["English", "marketing principles", "lead a team", "manage time"], "pay": (800, 1800)},
    "accountant": {"titles": ["Mühasib", "Бухгалтер", "Accountant"],
                   "core": ["accounting", "tax legislation", "financial statements", "use spreadsheets software", "International Financial Reporting Standards", "SAP R3", "assume responsibility", "Azerbaijani"],
                   "essential": ["accounting", "bookkeeping regulations", "prepare financial statements", "calculate tax", "check accounting records", "tax legislation", "financial statements"],
                   "optional": ["International Financial Reporting Standards", "financial analysis", "use spreadsheets software", "SAP R3"], "pay": (700, 1600)},
    "shop assistant": {"titles": ["Satıcı", "Продавец", "Shop Assistant"],
                       "core": ["customer service", "sales activities", "operate cash register", "Russian", "Azerbaijani", "work in teams", "assume responsibility"],
                       "essential": ["customer service", "operate cash register", "stock shelves", "maintain store cleanliness", "process payments", "sales activities"],
                       "optional": ["English", "communication", "cope with stress"], "pay": (450, 800)},
    "cashier": {"titles": ["Kassir", "Кассир", "Cashier"],
                "core": ["operate cash register", "customer service", "assume responsibility", "Russian", "work in teams"],
                "essential": ["operate cash register", "process payments", "customer service", "provide information"], "optional": ["cope with stress", "English"], "pay": (450, 750)},
    "software developer": {"titles": ["Proqramçı", "Software Developer", "Frontend Developer"],
                           "core": ["JavaScript", "TypeScript", "CSS", "SQL", "PostgreSQL", "Python", "Agile development", "English", "work in teams"],
                           "essential": ["JavaScript", "SQL", "Agile development", "data models"], "optional": ["TypeScript", "Python", "PostgreSQL", "MySQL", "machine learning"], "pay": (1500, 3500)},
    "data analyst": {"titles": ["Data Analyst", "Məlumat analitiki", "Аналитик данных"],
                     "core": ["SQL", "data analytics", "statistics", "Python", "use spreadsheets software", "think analytically", "English", "machine learning"],
                     "essential": ["data analytics", "statistics", "SQL", "think analytically", "data models"], "optional": ["Python", "machine learning", "use presentation software"], "pay": (1200, 2800)},
    "graphic designer": {"titles": ["Qrafik dizayner", "Graphic Designer", "Графический дизайнер"],
                         "core": ["graphic design", "Adobe Photoshop", "Adobe Illustrator", "social media management", "work independently", "manage time"],
                         "essential": ["graphic design", "Adobe Photoshop", "Adobe Illustrator"], "optional": ["social media management", "digital marketing techniques", "manage time"], "pay": (600, 1400)},
    "receptionist": {"titles": ["Resepşn", "Receptionist", "Администратор ресепшн"],
                     "core": ["customer service", "English", "Russian", "use microsoft office", "communication", "manage time"],
                     "essential": ["greet guests", "provide information", "customer service", "use microsoft office"], "optional": ["English", "Russian", "manage time"], "pay": (500, 900)},
    "warehouse worker": {"titles": ["Anbardar", "Кладовщик", "Warehouse Worker"],
                         "core": ["logistics", "manage inventory", "have computer literacy", "assume responsibility", "drive vehicles", "health and safety regulations"],
                         "essential": ["manage inventory", "logistics", "health and safety regulations"], "optional": ["drive vehicles", "have computer literacy"], "pay": (500, 900)},
    "barista": {"titles": ["Barista", "Бариста"],
                "core": ["customer service", "work in teams", "communication", "first aid"],
                "essential": ["customer service", "greet guests", "process payments"], "optional": ["English", "work in teams"], "pay": (400, 700)},
    "marketing manager": {"titles": ["Marketoloq", "Marketing Manager", "Маркетолог"],
                          "core": ["marketing principles", "digital marketing techniques", "social media management", "English", "think analytically", "use presentation software", "project management"],
                          "essential": ["marketing principles", "plan marketing campaigns", "perform market research", "digital marketing techniques"], "optional": ["social media management", "English", "data analytics"], "pay": (1000, 2200)},
    "project manager": {"titles": ["Layihə meneceri", "Project Manager", "Руководитель проекта"],
                        "core": ["project management", "lead a team", "manage time", "English", "negotiate with stakeholders", "Agile development", "use microsoft office"],
                        "essential": ["project management", "lead a team", "manage time", "negotiate with stakeholders"], "optional": ["Agile development", "English", "use CAD software"], "pay": (1300, 3000)},
    "commercial sales representative": {"titles": ["Satış təmsilçisi", "Торговый представитель"],
                                        "core": ["sales activities", "drive vehicles", "negotiate with stakeholders", "customer service", "Russian", "assume responsibility"],
                                        "essential": ["sales activities", "maintain relationship with customers", "achieve sales targets", "negotiate with stakeholders"], "optional": ["drive vehicles", "customer relationship management"], "pay": (600, 1200)},
    "human resources manager": {"titles": ["HR Manager", "İnsan resursları meneceri", "Менеджер по персоналу"],
                                "core": ["recruit employees", "human resource management", "communication", "English", "use microsoft office", "assume responsibility"],
                                "essential": ["recruit employees", "human resource management", "manage staff"], "optional": ["English", "communication"], "pay": (1000, 2000)},
    "office manager": {"titles": ["Ofis meneceri", "Офис-менеджер", "Office Manager"],
                       "core": ["use microsoft office", "use word processing software", "communication", "manage time", "Russian", "English"],
                       "essential": ["use microsoft office", "manage time", "provide information"], "optional": ["English", "use word processing software"], "pay": (600, 1100)},
}
WEIGHTS = {"sales manager": 60, "accountant": 50, "shop assistant": 45, "cashier": 25, "software developer": 30,
           "data analyst": 20, "graphic designer": 18, "receptionist": 18, "warehouse worker": 20, "barista": 15,
           "marketing manager": 20, "project manager": 18, "commercial sales representative": 25,
           "human resources manager": 15, "office manager": 15}

INTRO = {"az": ["Tələblər:", "Namizədə tələblər:", "Biz axtarırıq:"], "ru": ["Требования:", "Мы ожидаем:"], "en": ["Requirements:", "What we expect:"]}
DUTY = {"az": "Vəzifə öhdəlikləri: komandanın gündəlik işlərində iştirak, hesabatların hazırlanması.",
        "ru": "Обязанности: участие в ежедневной работе команды, подготовка отчётов.",
        "en": "Responsibilities: take part in the team's daily work and prepare reports."}
BOARDS = [("demo_board_a", "Demo Board A"), ("demo_board_b", "Demo Board B"), ("demo_board_c", "Demo Board C"),
          ("demo_board_d", "Demo Board D"), ("demo_board_e", "Demo Board E")]
COMPANY_A = ["Nümunə", "Example", "Sample", "Demo", "Fictional", "Placeholder"]
COMPANY_B = ["Trade", "Retail", "Finance", "Logistics", "Tech", "Foods", "Media", "Consulting", "Hotels", "Pharma"]
COMPANY_C = ["MMC", "LLC", "ASC"]


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def write_taxonomy(esco_dir: Path) -> None:
    esco_dir.mkdir(parents=True, exist_ok=True)
    with open(esco_dir / "skills_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["conceptType", "conceptUri", "skillType", "reuseLevel", "preferredLabel", "altLabels", "hiddenLabels",
                    "status", "modifiedDate", "scopeNote", "definition", "inScheme", "description"])
        for label, (stype, _) in SKILLS.items():
            alt = "CRM" if label == "customer relationship management" else ""
            w.writerow(["KnowledgeSkillCompetence", URI_SKILL + slug(label), stype, "", label, alt, "", "released", "", "", "",
                        "synthetic-demo", f"Synthetic demo concept '{label}' (not ESCO data)."])
    with open(esco_dir / "occupations_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["conceptType", "conceptUri", "iscoGroup", "preferredLabel", "altLabels", "hiddenLabels", "status",
                    "modifiedDate", "regulatedProfessionNote", "scopeNote", "definition", "inScheme", "description", "code"])
        for i, occ in enumerate(OCCUPATIONS):
            w.writerow(["Occupation", URI_OCC + slug(occ), "", occ, "", "", "released", "", "", "", "", "synthetic-demo",
                        f"Synthetic demo occupation '{occ}' (not ESCO data).", f"demo.{i}"])
    with open(esco_dir / "occupationSkillRelations_en.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["occupationUri", "relationType", "skillType", "skillUri"])
        for occ, d in OCCUPATIONS.items():
            for rel in ("essential", "optional"):
                for sk in d[rel]:
                    w.writerow([URI_OCC + slug(occ), rel, SKILLS[sk][0], URI_SKILL + slug(sk)])
    (esco_dir / "SYNTHETIC_DEMO_TAXONOMY.txt").write_text(
        "These CSV files are a small SYNTHETIC taxonomy generated by skillradar/demo_data.py for the demo.\n"
        "They use the ESCO CSV column layout but are NOT the ESCO dataset. URIs are synthetic (example.org).\n",
        encoding="utf-8")


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_jobs(n: int = 420, now: datetime | None = None) -> list[dict]:
    rnd = random.Random(SEED)
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    companies = sorted({f"{a} {b} {c}" for a in COMPANY_A for b in COMPANY_B for c in COMPANY_C})
    rnd.shuffle(companies)
    companies = companies[:70]
    occs = list(WEIGHTS)
    jobs = []
    for i in range(n):
        occ = rnd.choices(occs, weights=[WEIGHTS[o] for o in occs])[0]
        d = OCCUPATIONS[occ]
        lang = rnd.choices(["az", "ru", "en"], weights=[60, 15, 25])[0]
        title = rnd.choice(d["titles"])
        skills = rnd.sample(d["core"], k=min(len(d["core"]), rnd.randint(2, 6)))
        phrases = [rnd.choice(SKILLS[s][1][lang]) for s in skills if SKILLS[s][1]]
        has_text = rnd.random() > 0.07
        desc = f"{rnd.choice(INTRO[lang])} {', '.join(phrases)}. {DUTY[lang]}" if has_text else None
        board, board_name = rnd.choice(BOARDS)
        posted = now - timedelta(days=rnd.randint(0, 45), hours=rnd.randint(0, 20))
        sal_from = sal_to = currency = period = None
        if rnd.random() < 0.55:
            lo, hi = d["pay"]
            base = rnd.randrange(lo, hi, 50)
            shape = rnd.random()
            sal_from = base if shape < 0.85 else None
            sal_to = base + rnd.randrange(100, 900, 50) if shape > 0.15 else None
            currency, period = "AZN", ("MONTH" if rnd.random() < 0.45 else None)
        jid = f"{board}:{100000 + i}"
        jobs.append({
            "id": jid, "source": board, "source_name": board_name, "source_url": "https://example.com",
            "title": title, "company": {"name": rnd.choice(companies), "slug": None},
            "location": rnd.choice(["Bakı", "Bakı, Azərbaycan", "Baku, Azerbaijan"]), "city": "Bakı",
            "remote": None, "employment_type": rnd.choice(["Full-time", "FULL_TIME", "Part-time", "Internship", None]),
            "job_function": None, "career_level": None, "salary_from": sal_from, "salary_to": sal_to,
            "salary_currency": currency, "salary_period": period,
            "deadline_at": iso(posted + timedelta(days=30)) if rnd.random() < 0.5 else None,
            "posted_at": iso(posted), "url": f"https://example.com/demo/jobs/{100000 + i}",
            "description": desc, "requirements": None, "facts": {},
            "first_seen_at": iso(posted + timedelta(hours=2)), "times_seen": 1,
            "ingested_at": iso(now - timedelta(minutes=n - i)), "active": True,
            "contact_email": None, "contact_phone": None, "district": None, "country": "AZ",
        })
    # a few cross-board mirrors (same title, employer and date) to demonstrate deduplication
    for j in rnd.sample(jobs, k=12):
        other = rnd.choice([b for b in BOARDS if b[0] != j["source"]])
        m = dict(j, id=f"{other[0]}:{900000 + len(jobs)}", source=other[0], source_name=other[1],
                 url=f"https://example.com/demo/jobs/{900000 + len(jobs)}", first_seen_at=iso(now))
        jobs.append(m)
    return jobs


def generate(data_dir: Path, force: bool = False) -> dict:
    data_dir = Path(data_dir)
    target = data_dir / "raw" / "softon" / "synthetic_jobs.json"
    if target.exists() and not force:
        return {"skipped": True, "path": str(target)}
    write_taxonomy(data_dir / "raw" / "esco")
    jobs = generate_jobs()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"data": jobs, "meta": {"next": None, "count": len(jobs),
                                  "note": "SYNTHETIC DEMO DATA generated by skillradar/demo_data.py - not real vacancies"},
                                  "error": None}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"skipped": False, "vacancies": len(jobs), "skills": len(SKILLS), "occupations": len(OCCUPATIONS)}
