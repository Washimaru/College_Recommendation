/**
 * Major Finder dataset, ported from the original UniMatch project
 * (~/Claude/Projects/University_Recommendation_Project/js/majors.js).
 *
 * The MBTI field from the source is deliberately dropped - the same reasoning
 * that removed MBTI from the scoring model applies here.
 *
 * Axes describe how you like to work, and are distinct from the campus-culture
 * axes used for matching schools:
 *   people   0 = data / things      1 = people
 *   applied  0 = theoretical        1 = hands-on
 *   creative 0 = analytical         1 = creative / expressive
 *
 * Outcome figures are approximate; salary anchors from NACE Class of 2024
 * where noted, grad-school shares are rough estimates.
 */
export interface MajorOutcome {
  grad: string;
  salary: string;
  jobs: string[];
  note: string;
}

export interface MajorSpec {
  name: string;
  cat: string;
  courses: string[];
  /** Source of a case-insensitive regex matched against free-text activities. */
  act: string;
  axes: { people: number; applied: number; creative: number };
  blurb: string;
  out: MajorOutcome;
}

export const COURSE_TAGS = [
  "Math",
  "Statistics",
  "Biology",
  "Chemistry",
  "Physics",
  "Computer Science",
  "English / Literature",
  "History",
  "Economics",
  "Psychology",
  "Art",
  "Music",
  "Foreign Language",
  "Business",
  "Government / Politics",
  "Environmental Science",
  "Engineering / Tech",
  "Health / Anatomy"
] as const;

export const MAJORS: MajorSpec[] = [
  {
    "name": "Computer Science",
    "cat": "STEM",
    "courses": [
      "Computer Science",
      "Math",
      "Physics"
    ],
    "axes": {
      "people": 0.2,
      "applied": 0.6,
      "creative": 0.45
    },
    "blurb": "Designing software, algorithms and computing systems.",
    "out": {
      "grad": "~20% pursue a master's/PhD (est.)",
      "salary": "$89k median (NACE 2024)",
      "jobs": [
        "Software engineer",
        "Data scientist",
        "ML / AI engineer",
        "Product manager",
        "Security engineer"
      ],
      "note": "Very strong direct-to-industry hiring; graduate study mainly for research/ML specialties."
    },
    "act": "code|program|robot|hack|app|software|cyber|game"
  },
  {
    "name": "Data Science / Statistics",
    "cat": "STEM",
    "courses": [
      "Statistics",
      "Math",
      "Computer Science"
    ],
    "axes": {
      "people": 0.25,
      "applied": 0.55,
      "creative": 0.4
    },
    "blurb": "Turning data into models, predictions and insight.",
    "out": {
      "grad": "~30% pursue graduate study (est.)",
      "salary": "$80k+ median (est.)",
      "jobs": [
        "Data scientist",
        "Data / BI analyst",
        "Quantitative analyst",
        "ML engineer"
      ],
      "note": "Strong demand across tech, finance and healthcare; MS common for senior roles."
    },
    "act": "data|statist|analytic|machine learning|code"
  },
  {
    "name": "Mechanical / General Engineering",
    "cat": "Engineering",
    "courses": [
      "Math",
      "Physics",
      "Engineering / Tech"
    ],
    "axes": {
      "people": 0.3,
      "applied": 0.85,
      "creative": 0.5
    },
    "blurb": "Designing and building physical machines and systems.",
    "out": {
      "grad": "~22% pursue graduate study (est.)",
      "salary": "$80k avg for engineering (NACE 2024)",
      "jobs": [
        "Design engineer",
        "Mechanical engineer",
        "R&D engineer",
        "Manufacturing engineer"
      ],
      "note": "Mostly direct-to-industry; a PE license or MS helps for advanced roles."
    },
    "act": "engineer|build|robot|maker|cad|car|rocket"
  },
  {
    "name": "Electrical & Computer Engineering",
    "cat": "Engineering",
    "courses": [
      "Math",
      "Physics",
      "Computer Science",
      "Engineering / Tech"
    ],
    "axes": {
      "people": 0.25,
      "applied": 0.75,
      "creative": 0.45
    },
    "blurb": "Electronics, circuits, chips, signals and embedded systems.",
    "out": {
      "grad": "~25% pursue graduate study (est.)",
      "salary": "$85k+ (est.)",
      "jobs": [
        "Hardware engineer",
        "Embedded systems engineer",
        "Chip designer",
        "Robotics engineer"
      ],
      "note": "High demand in semiconductors, robotics and defense."
    },
    "act": "circuit|electron|robot|code|hardware|engineer"
  },
  {
    "name": "Biomedical Engineering",
    "cat": "Engineering",
    "courses": [
      "Biology",
      "Math",
      "Physics",
      "Engineering / Tech"
    ],
    "axes": {
      "people": 0.4,
      "applied": 0.75,
      "creative": 0.5
    },
    "blurb": "Applying engineering to medicine and biology.",
    "out": {
      "grad": "~40% pursue graduate/professional school (est.)",
      "salary": "$70k (est.)",
      "jobs": [
        "Biomedical / device engineer",
        "R&D engineer",
        "Clinical engineer",
        "(often pre-med)"
      ],
      "note": "Common springboard to medical school or a bioengineering PhD."
    },
    "act": "bio|medic|device|engineer|lab|research"
  },
  {
    "name": "Biology",
    "cat": "Life Sciences",
    "courses": [
      "Biology",
      "Chemistry",
      "Math",
      "Health / Anatomy"
    ],
    "axes": {
      "people": 0.4,
      "applied": 0.5,
      "creative": 0.35
    },
    "blurb": "The study of living systems, from molecules to ecosystems.",
    "out": {
      "grad": "~50%+ continue to medical or graduate school (est.)",
      "salary": "$45–55k with a bachelor's (est.)",
      "jobs": [
        "Lab / research technician",
        "Then physician, dentist, pharmacist or PhD scientist"
      ],
      "note": "A bachelor's alone is entry-level; most careers open up after med/grad school."
    },
    "act": "bio|lab|research|medic|hospital|health|environment"
  },
  {
    "name": "Chemistry",
    "cat": "Life Sciences",
    "courses": [
      "Chemistry",
      "Math",
      "Physics",
      "Biology"
    ],
    "axes": {
      "people": 0.25,
      "applied": 0.55,
      "creative": 0.4
    },
    "blurb": "Matter, reactions and molecular design.",
    "out": {
      "grad": "~45% pursue graduate study (est.)",
      "salary": "$50–60k (est.)",
      "jobs": [
        "Lab chemist",
        "Quality / process chemist",
        "R&D scientist (with PhD)"
      ],
      "note": "Research and higher pay generally require a PhD."
    },
    "act": "chem|lab|research|material"
  },
  {
    "name": "Physics",
    "cat": "Life Sciences",
    "courses": [
      "Physics",
      "Math",
      "Computer Science"
    ],
    "axes": {
      "people": 0.2,
      "applied": 0.4,
      "creative": 0.45
    },
    "blurb": "The fundamental laws of the universe.",
    "out": {
      "grad": "~55% pursue graduate/PhD study (est.)",
      "salary": "$65k (est.; higher in tech/finance)",
      "jobs": [
        "Research scientist",
        "Data scientist / quant",
        "Engineer",
        "Academia (with PhD)"
      ],
      "note": "Strong quantitative skills transfer into tech, finance and data roles."
    },
    "act": "physic|astro|research|olympiad|quantum"
  },
  {
    "name": "Mathematics",
    "cat": "STEM",
    "courses": [
      "Math",
      "Statistics",
      "Computer Science"
    ],
    "axes": {
      "people": 0.2,
      "applied": 0.4,
      "creative": 0.4
    },
    "blurb": "Abstract structures, logic and quantitative reasoning.",
    "out": {
      "grad": "~40% pursue graduate study (est.)",
      "salary": "$70k (est.; strong in tech & finance)",
      "jobs": [
        "Actuary",
        "Quantitative analyst",
        "Data scientist",
        "Software engineer"
      ],
      "note": "Very flexible; pairs well with CS, economics or finance."
    },
    "act": "math|olympiad|proof|puzzle|code"
  },
  {
    "name": "Neuroscience",
    "cat": "Life Sciences",
    "courses": [
      "Biology",
      "Chemistry",
      "Psychology",
      "Health / Anatomy"
    ],
    "axes": {
      "people": 0.45,
      "applied": 0.5,
      "creative": 0.4
    },
    "blurb": "The biology of the brain, behavior and cognition.",
    "out": {
      "grad": "~55% continue to medical or graduate school (est.)",
      "salary": "$50k with a bachelor's (est.)",
      "jobs": [
        "Research assistant",
        "Then physician, PhD researcher or clinician"
      ],
      "note": "A popular pre-med and pre-PhD track."
    },
    "act": "neuro|brain|bio|research|psych|medic"
  },
  {
    "name": "Nursing",
    "cat": "Health",
    "courses": [
      "Biology",
      "Chemistry",
      "Health / Anatomy",
      "Psychology"
    ],
    "axes": {
      "people": 0.85,
      "applied": 0.85,
      "creative": 0.3
    },
    "blurb": "Direct, hands-on patient care and health.",
    "out": {
      "grad": "~15% pursue advanced practice (NP/CRNA) (est.)",
      "salary": "$75–85k (est.)",
      "jobs": [
        "Registered nurse",
        "Then nurse practitioner or specialist (with grad study)"
      ],
      "note": "Strong, stable job market straight out of a BSN."
    },
    "act": "nurs|health|hospital|medic|care|volunteer"
  },
  {
    "name": "Public Health",
    "cat": "Health",
    "courses": [
      "Biology",
      "Statistics",
      "Health / Anatomy",
      "Psychology"
    ],
    "axes": {
      "people": 0.75,
      "applied": 0.55,
      "creative": 0.35
    },
    "blurb": "Population health, prevention and health policy.",
    "out": {
      "grad": "~45% pursue an MPH or related graduate degree (est.)",
      "salary": "$50k with a bachelor's (est.)",
      "jobs": [
        "Health educator",
        "Program coordinator",
        "Epidemiologist (with MPH)",
        "Policy analyst"
      ],
      "note": "An MPH substantially expands roles and pay."
    },
    "act": "health|public|epidem|community|policy|volunteer"
  },
  {
    "name": "Psychology",
    "cat": "Social Sciences",
    "courses": [
      "Psychology",
      "Biology",
      "Statistics"
    ],
    "axes": {
      "people": 0.85,
      "applied": 0.5,
      "creative": 0.4
    },
    "blurb": "The science of mind and behavior.",
    "out": {
      "grad": "~44% pursue graduate study (APA)",
      "salary": "$45k with a bachelor's (est.)",
      "jobs": [
        "HR / people ops",
        "Research assistant",
        "UX researcher",
        "Counselor / therapist (with grad degree)"
      ],
      "note": "Clinical and counseling careers require graduate school."
    },
    "act": "psych|counsel|mental|research|volunteer|people"
  },
  {
    "name": "Economics",
    "cat": "Social Sciences",
    "courses": [
      "Economics",
      "Math",
      "Statistics",
      "Government / Politics"
    ],
    "axes": {
      "people": 0.5,
      "applied": 0.5,
      "creative": 0.35
    },
    "blurb": "How people, markets and policy allocate resources.",
    "out": {
      "grad": "~25% pursue graduate study (est.)",
      "salary": "$65–70k (est.)",
      "jobs": [
        "Financial analyst",
        "Consultant",
        "Economist",
        "Data analyst"
      ],
      "note": "A strong feeder into finance, consulting and public policy."
    },
    "act": "econ|invest|business|policy|debate|stock|research"
  },
  {
    "name": "Business / Management",
    "cat": "Business",
    "courses": [
      "Business",
      "Economics",
      "Math"
    ],
    "axes": {
      "people": 0.75,
      "applied": 0.7,
      "creative": 0.4
    },
    "blurb": "Running, growing and leading organizations.",
    "out": {
      "grad": "~20% later pursue an MBA (est.)",
      "salary": "$69k avg for business (NACE 2024)",
      "jobs": [
        "Business analyst",
        "Operations associate",
        "Marketing / sales",
        "Management trainee"
      ],
      "note": "Broad, people-facing; an MBA often comes a few years into a career."
    },
    "act": "business|startup|entrepreneur|market|deca|invest|manage"
  },
  {
    "name": "Finance / Accounting",
    "cat": "Business",
    "courses": [
      "Business",
      "Economics",
      "Math",
      "Statistics"
    ],
    "axes": {
      "people": 0.55,
      "applied": 0.65,
      "creative": 0.25
    },
    "blurb": "Money, markets, investment and financial reporting.",
    "out": {
      "grad": "~15% (plus CPA/CFA credentials) (est.)",
      "salary": "$70k (est.)",
      "jobs": [
        "Financial analyst",
        "Accountant / auditor",
        "Investment banking analyst",
        "Advisor"
      ],
      "note": "Professional credentials (CPA, CFA) matter more than a graduate degree."
    },
    "act": "finance|account|invest|stock|business|audit"
  },
  {
    "name": "Marketing / Communications",
    "cat": "Business",
    "courses": [
      "Business",
      "English / Literature",
      "Psychology"
    ],
    "axes": {
      "people": 0.8,
      "applied": 0.7,
      "creative": 0.7
    },
    "blurb": "Brand, storytelling, audience and media.",
    "out": {
      "grad": "~12% pursue graduate study (est.)",
      "salary": "$55k (est.)",
      "jobs": [
        "Marketing coordinator",
        "Social media / content",
        "PR specialist",
        "Brand manager"
      ],
      "note": "Portfolio and internships weigh heavily in hiring."
    },
    "act": "market|communic|social media|advertis|brand|pr|writ"
  },
  {
    "name": "Political Science",
    "cat": "Social Sciences",
    "courses": [
      "Government / Politics",
      "History",
      "English / Literature"
    ],
    "axes": {
      "people": 0.7,
      "applied": 0.4,
      "creative": 0.4
    },
    "blurb": "Government, power, policy and political behavior.",
    "out": {
      "grad": "~35–40% continue to graduate or law school (est.)",
      "salary": "$50k with a bachelor's (est.)",
      "jobs": [
        "Policy analyst",
        "Legislative / campaign staff",
        "Government / NGO",
        "Then law school"
      ],
      "note": "A very common pre-law path."
    },
    "act": "politic|debate|model un|mun|government|policy|campaign|law"
  },
  {
    "name": "International Relations",
    "cat": "Social Sciences",
    "courses": [
      "Government / Politics",
      "History",
      "Foreign Language",
      "Economics"
    ],
    "axes": {
      "people": 0.7,
      "applied": 0.4,
      "creative": 0.4
    },
    "blurb": "Diplomacy, global affairs and cross-border policy.",
    "out": {
      "grad": "~40% pursue graduate study (est.)",
      "salary": "$52k (est.)",
      "jobs": [
        "Foreign / civil service",
        "NGO / international org",
        "Analyst",
        "Consultant"
      ],
      "note": "Language skills and a graduate degree strengthen prospects."
    },
    "act": "international|diplomacy|model un|mun|global|policy|language"
  },
  {
    "name": "English / Literature",
    "cat": "Humanities",
    "courses": [
      "English / Literature",
      "History",
      "Foreign Language"
    ],
    "axes": {
      "people": 0.55,
      "applied": 0.35,
      "creative": 0.85
    },
    "blurb": "Literature, language, rhetoric and critical thinking.",
    "out": {
      "grad": "~30% pursue graduate or law school (est.)",
      "salary": "$45k (est.)",
      "jobs": [
        "Writer / editor",
        "Content strategist",
        "Teacher",
        "Then law or an MA"
      ],
      "note": "Strong writing transfers widely; many pivot to law, comms or education."
    },
    "act": "writ|read|literary|poetry|journal|book|debate"
  },
  {
    "name": "History",
    "cat": "Humanities",
    "courses": [
      "History",
      "English / Literature",
      "Government / Politics"
    ],
    "axes": {
      "people": 0.45,
      "applied": 0.3,
      "creative": 0.55
    },
    "blurb": "The human past, evidence and interpretation.",
    "out": {
      "grad": "~35% pursue graduate or law school (est.)",
      "salary": "$48k (est.)",
      "jobs": [
        "Analyst / researcher",
        "Educator",
        "Archivist / museum",
        "Then law or academia"
      ],
      "note": "Builds research and argument skills valued in law and policy."
    },
    "act": "histor|research|debate|writ|museum|archive"
  },
  {
    "name": "Philosophy",
    "cat": "Humanities",
    "courses": [
      "English / Literature",
      "Math",
      "History"
    ],
    "axes": {
      "people": 0.4,
      "applied": 0.2,
      "creative": 0.6
    },
    "blurb": "Logic, ethics, knowledge and the big questions.",
    "out": {
      "grad": "~40% pursue law or graduate school (est.)",
      "salary": "$48k (est.)",
      "jobs": [
        "Analyst",
        "Then law school (top LSAT scores)",
        "Tech / policy",
        "Academia"
      ],
      "note": "Philosophy majors post some of the highest law-school entrance scores."
    },
    "act": "philosoph|debate|ethics|logic|argument|writ"
  },
  {
    "name": "Sociology / Social Work",
    "cat": "Social Sciences",
    "courses": [
      "Psychology",
      "Government / Politics",
      "Statistics"
    ],
    "axes": {
      "people": 0.9,
      "applied": 0.55,
      "creative": 0.4
    },
    "blurb": "Society, communities and helping people.",
    "out": {
      "grad": "~40% pursue an MSW or graduate study (est.)",
      "salary": "$45k (est.)",
      "jobs": [
        "Case manager",
        "Community / nonprofit",
        "Social worker (with MSW)",
        "Policy / research"
      ],
      "note": "Licensed social work requires an MSW."
    },
    "act": "social|community|volunteer|nonprofit|advoca|justice|care"
  },
  {
    "name": "Education",
    "cat": "Social Sciences",
    "courses": [
      "English / Literature",
      "Psychology",
      "History"
    ],
    "axes": {
      "people": 0.9,
      "applied": 0.75,
      "creative": 0.55
    },
    "blurb": "Teaching, learning and child development.",
    "out": {
      "grad": "~35% pursue a master's (often for licensure/raises) (est.)",
      "salary": "$45k (est.)",
      "jobs": [
        "K-12 teacher",
        "Instructional coordinator",
        "Ed-tech",
        "School counselor (with grad)"
      ],
      "note": "Steady demand; a master's often boosts pay and roles."
    },
    "act": "teach|tutor|education|coach|mentor|kids"
  },
  {
    "name": "Art & Design",
    "cat": "Arts",
    "courses": [
      "Art"
    ],
    "axes": {
      "people": 0.4,
      "applied": 0.7,
      "creative": 0.95
    },
    "blurb": "Visual art, design and creative craft.",
    "out": {
      "grad": "~15% pursue an MFA (est.)",
      "salary": "$45–50k (est.)",
      "jobs": [
        "Graphic / UX designer",
        "Illustrator",
        "Art director",
        "Product designer"
      ],
      "note": "A strong portfolio matters far more than a graduate degree."
    },
    "act": "art|paint|draw|design|photograph|graphic|illustrat"
  },
  {
    "name": "Music",
    "cat": "Arts",
    "courses": [
      "Music"
    ],
    "axes": {
      "people": 0.5,
      "applied": 0.75,
      "creative": 0.95
    },
    "blurb": "Performance, composition and the music industry.",
    "out": {
      "grad": "~25% pursue a graduate conservatory degree (est.)",
      "salary": "Varies widely (est.)",
      "jobs": [
        "Performer",
        "Music teacher",
        "Producer / engineer",
        "Music business"
      ],
      "note": "Careers vary from performance to production to education."
    },
    "act": "music|band|orchestra|choir|jazz|instrument|compos|produc"
  },
  {
    "name": "Film / Theatre",
    "cat": "Arts",
    "courses": [
      "Art",
      "English / Literature",
      "Music"
    ],
    "axes": {
      "people": 0.7,
      "applied": 0.75,
      "creative": 0.95
    },
    "blurb": "Storytelling through screen and stage.",
    "out": {
      "grad": "~15% pursue graduate arts study (est.)",
      "salary": "$45k (est.; highly variable)",
      "jobs": [
        "Production crew",
        "Editor / videographer",
        "Actor / performer",
        "Screenwriter"
      ],
      "note": "Freelance and project-based work is common early on."
    },
    "act": "film|theat|drama|acting|cinema|dance|video"
  },
  {
    "name": "Architecture",
    "cat": "Arts",
    "courses": [
      "Art",
      "Math",
      "Physics"
    ],
    "axes": {
      "people": 0.5,
      "applied": 0.85,
      "creative": 0.85
    },
    "blurb": "Designing buildings and spaces.",
    "out": {
      "grad": "~60% pursue an M.Arch (needed for licensure) (est.)",
      "salary": "$55k early-career (est.)",
      "jobs": [
        "Architectural designer",
        "Then licensed architect",
        "Urban / interior design"
      ],
      "note": "Licensure requires a professional degree + exams."
    },
    "act": "architect|design|build|draw|cad|urban"
  },
  {
    "name": "Environmental Science",
    "cat": "Life Sciences",
    "courses": [
      "Environmental Science",
      "Biology",
      "Chemistry"
    ],
    "axes": {
      "people": 0.45,
      "applied": 0.6,
      "creative": 0.35
    },
    "blurb": "Ecosystems, climate and sustainability.",
    "out": {
      "grad": "~35% pursue graduate study (est.)",
      "salary": "$50k (est.)",
      "jobs": [
        "Environmental analyst",
        "Sustainability specialist",
        "Field / lab scientist",
        "Policy / NGO"
      ],
      "note": "Government agencies and consulting are major employers."
    },
    "act": "environment|sustain|climate|ecology|outdoors|conservation"
  }
];
