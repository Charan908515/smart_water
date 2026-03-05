"""
Configuration settings for Smart Water Intake System
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Weather API Configuration (Open-Meteo)
WEATHER_CACHE_DURATION = 1800  # Cache weather data for 30 minutes (in seconds)
WEATHER_GEO_COUNTRY_CODE = os.getenv('WEATHER_GEO_COUNTRY_CODE', 'IN')

# Sweat Calibration Settings
SWEAT_CALIBRATION_DAYS = 7  # Number of days required for calibration
SWEAT_MIN_VALUE = 0.0  # Minimum sweat reading (arbitrary units)
SWEAT_MAX_VALUE = 100.0  # Maximum sweat reading (arbitrary units)

# Hydration Level Thresholds (as percentage of recommended intake)
HYDRATION_EXCELLENT = 1.0  # 100%+ of recommended
HYDRATION_GOOD = 0.8  # 80-100%
HYDRATION_ADEQUATE = 0.6  # 60-80%
HYDRATION_LOW = 0.4  # 40-60%
# Below 40% is considered dehydrated

# Weather Adjustment Factors
WEATHER_ADJUSTMENT = {
    'Hot': 1.15,      # +15% water needed in hot weather
    'Normal': 1.0,    # No adjustment
    'Cold': 0.9       # -10% water needed in cold weather
}

# Activity Level Adjustment Factors
ACTIVITY_ADJUSTMENT = {
    'High': 1.2,      # +20% water needed for high activity
    'Moderate': 1.0,  # No adjustment
    'Low': 0.9        # -10% water needed for low activity
}

# Activity baseline average used until 7 full days of readings are available
ACTIVITY_BASELINE_AVG = 72

# Temperature thresholds for weather classification (Celsius)
TEMP_HOT_THRESHOLD = 28  # Above 28°C is considered hot
TEMP_COLD_THRESHOLD = 15  # Below 15°C is considered cold

# Water intake recommended ratio (liters per kg body weight)
WATER_PER_KG = 0.033

# Default location if not specified
DEFAULT_LOCATION = "New York"
