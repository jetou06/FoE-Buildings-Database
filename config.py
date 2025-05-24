import logging

# --- Logging Setup ---
# Basic configuration (can be customized further if needed)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Optional: Add file handler if persistent logging is desired outside Streamlit console
# logfile = logging.FileHandler('logfile.log')
# logfile.setLevel(logging.INFO)
# formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
# logfile.setFormatter(formatter)
# logger.addHandler(logfile)

# --- File Paths ---
METADATA_FILE_PATH_TEMPLATE = r'metadata-zz0-129.json' # Use double backslashes or raw string
DB_PATH = 'foe_buildings.db'
ASSETS_PATH = 'assets' # Relative path assumed from app root

# --- Game Data Constants ---
ERAS_DICT = {
    "SpaceAgeSpaceHub": "Space Age: Space Hub",
    "SpaceAgeTitan": "Space Age: Titan",
    "SpaceAgeJupiterMoon": "Space Age: Jupiter Moon",
    "SpaceAgeVenus": "Space Age: Venus",
    "SpaceAgeAsteroidBelt": "Space Age: Asteroid Belt",
    "SpaceAgeMars": "Space Age: Mars",
    "VirtualFuture": "Future: Virtual",
    "OceanicFuture": "Oceanic Future",
    "ArcticFuture": "Arctic Future",
    "FutureEra": "Future Era",
    "TomorrowEra": "Tomorrow Era",
    "ContemporaryEra": "Contemporary Era",
    "PostModernEra": "Post-Modern Era",
    "ModernEra": "Modern Era",
    "ProgressiveEra": "Progressive Era",
    "IndustrialAge": "Industrial Age",
    "ColonialAge": "Colonial Age",
    "LateMiddleAge": "Late Middle Age",
    "HighMiddleAge": "High Middle Age",
    "EarlyMiddleAge": "Early Middle Age",
    "IronAge": "Iron Age",
    "BronzeAge": "Bronze Age"
}

# Columns that represent outputs for weighting
WEIGHTABLE_COLUMNS = [
    "forge_points", "forgepoint_package",
    "goods", "next_age_goods", "prev_age_goods", "special_goods", "guild_goods",
    "rogues", "fast_units", "heavy_units", "ranged_units", "artillery_units", "light_units",
    "next_age_fast_units", "next_age_heavy_units", "next_age_ranged_units", "next_age_artillery_units", "next_age_light_units",
    "Population",
    "Red Attack", "Red Defense", "Blue Attack", "Blue Defense",
    "Red GBG Attack", "Red GBG Defense", "Blue GBG Attack", "Blue GBG Defense",
    "Red GE Attack", "Red GE Defense", "Blue GE Attack", "Blue GE Defense",
    "Red QI Attack", "Red QI Defense", "Blue QI Attack", "Blue QI Defense",
    "QI Coin %", "QI Coin at start", "QI Supplies %", "QI Supplies at start", "QI Goods at start", "QI Units at start", "QA per hour",
    "FP boost", "Guild Goods Production %", "Special Goods Production %", "Medal Boost", "Goods Boost"
]

# Define column groups (moved from app logic)
# Note: Translations for the display names will be handled by the translation module
COLUMN_GROUPS = {
    "basic_info": {
        "key": "basic_info", # Use key for referencing
        "columns": ["Event", "Translated Era", "Weighted Efficiency", "Total Score", "size", "Nbr of squares (Avg)", "Road", "Limited", "Ally room", "Population", "Happiness"]
    },
    "production": {
        "key": "production",
        "columns": ["coins", "supplies", "medals", "forge_points", "forgepoint_package", "goods",
                    "next_age_goods", "prev_age_goods", "special_goods", "guild_goods"]
    },
    "military": {
        "key": "military",
        "columns": ["rogues", "fast_units", "heavy_units", "ranged_units", "artillery_units", "light_units", "next_age_fast_units", "next_age_heavy_units", "next_age_ranged_units", "next_age_artillery_units", "next_age_light_units"]
    },
    "base_army": {
        "key": "base_army",
        "columns": ["Red Attack", "Red Defense", "Blue Attack", "Blue Defense"]
    },
    "gbg": {
        "key": "gbg",
        "columns": ["Red GBG Attack", "Red GBG Defense", "Blue GBG Attack", "Blue GBG Defense"]
    },
    "ge": {
        "key": "ge",
        "columns": ["Red GE Attack", "Red GE Defense", "Blue GE Attack", "Blue GE Defense"]
    },
    "qi": {
        "key": "qi",
        "columns": ["Red QI Attack", "Red QI Defense", "Blue QI Attack", "Blue QI Defense",
                    "QI Coin %", "QI Coin at start", "QI Supplies %", "QI Supplies at start", "QI Goods at start", "QI Units at start", "QA per hour"]
    },
    "boosts": {
        "key": "boosts",
        "columns": ["Coin %", "Supplies %", "FP boost", "Guild Goods Production %",
                    "Special Goods Production %", "Medal Boost", "Goods Boost"]
    },
    "other": {
        "key": "other",
        "columns": ["Other productions"]
    }
}

# Columns to exclude from certain operations (like icon loading or per-square calc)
ICON_EXCLUDED_COLUMNS = {
    'name', 'Event', 'Translated Era', 'size', 'Total Score',
    'Nbr of squares (Avg)', 'Limited', 'Ally room',
    'Unit type', 'Next Age Unit type', 'Other productions',
    'Weighted Efficiency'
}

PER_SQUARE_EXCLUDED_COLUMNS = [
    'name', 'Event', 'Translated Era', 'Nbr of squares (Avg)', 'Road', 'Limited', 'Ally room', 'size',
    'Unit type', 'Next Age Unit type', 'Other productions', 'Weighted Efficiency', 'Total Score'
]

# Columns formatted as percentages
PERCENTAGE_COLUMNS = {
    "Red Attack", "Red Defense", "Blue Attack", "Blue Defense",
    "Red GBG Attack", "Red GBG Defense", "Blue GBG Attack", "Blue GBG Defense",
    "Red GE Attack", "Red GE Defense", "Blue GE Attack", "Blue GE Defense",
    "Red QI Attack", "Red QI Defense", "Blue QI Attack", "Blue QI Defense",
    "QI Coin %", "QI Supplies %",
    "Coin %", "Supplies %", "FP boost", "Guild Goods Production %",
    "Special Goods Production %", "Medal Boost", "Goods Boost"
} 