# Site list. Each entry picks a scraping mode:
#   links      - collect <a> links matching `pattern` (render=True uses a real browser for JS sites)
#   section    - vacancies printed inline on one page (no per-vacancy links)
#   wordpress  - WordPress category via REST API / RSS
#   workday    - Workday JSON API
#   eightfold  - Eightfold JSON API
#   phenom     - Phenom career sites (embedded JSON, falls back to links)
#
# `country`/`location`: global companies are limited to Kazakhstan.
# Delete that line to receive every new job worldwide.

SITES = [
    {
        "name": "NCOC",
        "mode": "links",
        "render": True,
        "url": "https://career2.successfactors.eu/career?company=ncocnv&site=VjQtMC1hMS16MTRydW1Pc3RLT3dMcUpWZkZIUWRCNG1DMWdBdVd5dWRVT0RZX2hqOUE=&rcm_site_locale=ru_RU",
        "pattern": r"career_job_req_id=\d+",
        "id_regex": r"career_job_req_id=(\d+)",
    },
    {
        "name": "Samruk-Kazyna (qsamruk)",
        "mode": "links",
        "pages": [
            "https://qsamruk.kz/vacancy",
            "https://qsamruk.kz/vacancy?page=2",
            "https://qsamruk.kz/vacancy?page=3",
        ],
        "pattern": r"qsamruk\.kz/vacancy/\d+/?$",
        "id_regex": r"/vacancy/(\d+)",
    },
    {
        "name": "Bolashak",
        "mode": "links",
        "url": "https://bolashak.gov.kz/ru/vakansii",
        "pattern": r"bolashak\.gov\.kz/ru/vakansii/[^/?#]+/?$",
        "exclude": r"rezultaty",
    },
    {
        "name": "Ten Oil",
        "mode": "wordpress",
        "base": "https://tenoil.kz",
        "category": "career",
    },
    {
        "name": "KazTransOil",
        "mode": "section",
        "url": "https://kaztransoil.kz/ru/o_kompanii/vacancy/",
        "start": "Открытые вакансии",
        "end": "Закрытые вакансии",
        "anchor": r"Сроки при[её]ма",
    },
    {
        "name": "Silleno",
        "mode": "links",
        "pages": [f"https://silleno.taphr.kz/?page={n}" for n in range(1, 5)],
        "pattern": r"silleno\.taphr\.kz/vacancy/\d+",
        "id_regex": r"/vacancy/(\d+)",
    },
    {
        "name": "Worley",
        "mode": "eightfold",
        "base": "https://jobs.worley.com",
        "domain": "worley.com",
        "location": "Kazakhstan",
    },
    {
        "name": "KPO",
        "mode": "links",
        "render": True,
        "url": "https://hr.kpo.kz/",
        "pattern": r"hr\.kpo\.kz/.*(vacanc|vakans|job|position)",
        # if the cards have no links, read titles from page text instead
        "fallback": {"mode": "section", "anchor": r"\b\d{1,2}\s*/\s*\d{1,2}\b"},
    },
    {
        "name": "FIR Caspian",
        "mode": "links",
        "url": "https://fircaspian.com/ru/jobs",
        "pattern": r"fircaspian\.com/ru/job/\d+",
        "id_regex": r"/job/(\d+)",
    },
    {
        "name": "NES Fircroft (oil & gas)",
        "mode": "cards",
        "render": True,
        "url": "https://www.nesfircroft.com/job-search/?industry=oil--gas",
        "card": "li.job-data",
        "title": ".xs-heading",
        "location_sel": ".icon.location + span",
    },
    {
        "name": "SLB",
        "mode": "links",
        "render": True,
        "url": "https://careers.slb.com/job-listing#q=Kazakhstan&cq=%40source%3D%3D%24%22ATS_Jobs_Source%20-%20Prod%22",
        "pattern": r"(job-detail|jobdescription|jobaddetail|jobid=|career_job_req_id|/job/)",
        "exclude": r"job-categories|job-listing",
        "id_regex": r"(?:jobid|id)=([\w-]+)",
    },
    {
        "name": "PwC Kazakhstan",
        "mode": "phenom",
        "url": "https://jobs-cee.pwc.com/ea/en/search-results-kazakhstan",
        "job_base": "https://jobs-cee.pwc.com/ea/en/job/",
    },
    {
        "name": "KPMG Caucasus & Central Asia",
        "mode": "links",
        "render": True,
        "click_more": r"Show more|Показать ещ|Load more",
        "url": "https://kpmgcca.global.huntflow.io/",
        "pattern": r"kpmgcca\.global\.huntflow\.io/vacancy/[^/?#]+",
    },
    {
        "name": "Baker Hughes",
        "mode": "phenom",
        "url": "https://careers.bakerhughes.com/global/en/search-results?keywords=Kazakhstan",
        "job_base": "https://careers.bakerhughes.com/global/en/job/",
        "location": "Kazakhstan",
    },
    {
        "name": "Halliburton Kazakhstan",
        "mode": "links",
        "url": "https://careers.halliburton.com/location/kazakhstan-jobs/543/1522867/2",
        "pattern": r"careers\.halliburton\.com/job/.+/\d{6,}",
        "id_regex": r"/(\d{6,})/?$",
    },
    {
        "name": "Shell",
        "mode": "workday",
        "host": "shell.wd3.myworkdayjobs.com",
        "tenant": "shell",
        "site": "shellcareers",
        "country": "Kazakhstan",
    },
    {
        "name": "AtyrauTechInvest",
        "mode": "cards",
        "url": "https://dreamjob.ru/employers/196260/vakansii",
        "card": "div.vacancy",
        "title": "h3.vacancy__head",
        "link_attr": "data-link",
        "id_regex": r"/(\d+)/?$",
        "link_template": "https://hh.kz/vacancy/{id}",
        "exp_sel": ".tags__item",
        "location_sel": ".vacancy__city",
    },
    {
        "name": "ANPZ (Atyrau Refinery)",
        "mode": "links",
        "url": "https://www.anpz.kz/vacancies/",
        "pattern": r"anpz\.kz/vacancies/[^?#]+",
        "exclude": r"(summary|obrazec|register|\.docx?$|\.pdf$)",
        "fallback": {"mode": "section", "start": "Открыта до", "end": "Этапы отбора",
                     "anchor": r"\d{2}\.\d{2}\.\d{4}"},
    },
    {
        "name": "KMG",
        "mode": "links",
        "render": True,
        "url": "https://work.kmg.kz/vacancies",
        "pattern": r"work\.kmg\.kz/vacanc\w*/[^?#]+",
    },
]
