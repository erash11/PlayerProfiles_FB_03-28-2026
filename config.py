from pathlib import Path

# Root of this project
PROJECT_ROOT = Path(__file__).parent

# --- Data source paths ---
FORCEPLATE_DB = Path(
    "C:/Users/eric_rash/Desktop/DEV/ForcePlate_DecisionSystem/data/forceplate.db"
)
GPS_DB = Path(
    "C:/Users/eric_rash/Desktop/DEV/DataBase_GPS_Reporting/gps_report/data/gps_history.duckdb"
)
BODYWEIGHT_CSV = Path(
    "C:/Users/eric_rash/Desktop/DEV/Football/BodWeightWeb/BodyWeightMaster.csv"
)
ROSTER_CSV = PROJECT_ROOT / "data" / "athlete_roster.csv"

# --- Output ---
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
