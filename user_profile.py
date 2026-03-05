import os
from datetime import datetime, timedelta
import numpy as np
import bcrypt
from database import get_db
import config


def find_profile_by_mac(mac_id: str):
    """Search MongoDB for a profile matching the given mac_id (last 6 chars)."""
    mac_id = mac_id.upper().strip()[-6:]
    db = get_db()
    if db is None:
        return None

    user_data = db.users.find_one({'mac_id': mac_id})
    if user_data:
        return UserProfile(user_data['user_id'], preload_data=user_data)
    return None


class UserProfile:

    def __init__(self, user_id, preload_data=None):
        self.user_id = user_id
        self.db = get_db()
        if preload_data:
            self.data = preload_data
        else:
            self.data = self._load_or_create()

    def _load_or_create(self):
        if self.db is None:
            return self._default_schema()
            
        existing = self.db.users.find_one({'user_id': self.user_id})
        if existing:
            return existing
        else:
            return self._default_schema()

    def _default_schema(self):
        return {
            'user_id': self.user_id,
            'mac_id': '',
            'password_hash': None,
            'created_at': datetime.now().isoformat(),
            'base_info': {},
            'location': '',
            'coords': None,           # {"latitude": float, "longitude": float, "updated_at": iso}
            'activity_history': [],   # [{"timestamp": ..., "value": numeric}, ...]
            'water_log': [],          # [{"timestamp": ..., "amount": liters}, ...]
            'weather_history': [],    # [{"timestamp": ..., "temperature": C, "condition": ...}, ...]
            'daily_records': [],
            'personalization': {
                'risk_adjustment': 0,
                'is_calibrated': False,
                'calibration_date': None
            }
        }

    def save(self):
        """Upsert the profile data into MongoDB."""
        if self.db is not None:
            # We don't want to save the _id back if it's there but we just constructed a new document
            data_to_save = {k: v for k, v in self.data.items() if k != '_id'}
            self.db.users.update_one(
                {'user_id': self.user_id},
                {'$set': data_to_save},
                upsert=True
            )

    # ---------- Authentication ----------

    def set_password(self, plain_password: str):
        """Hash and store a new password."""
        salt = bcrypt.gensalt()
        self.data['password_hash'] = bcrypt.hashpw(plain_password.encode('utf-8'), salt).decode('utf-8')
        self.save()

    def verify_password(self, plain_password: str) -> bool:
        """Verify the given password against the stored hash."""
        hashed = self.data.get('password_hash')
        if not hashed:
            return False
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed.encode('utf-8'))
        
    def has_password(self) -> bool:
        """Check if this profile has a password set."""
        return bool(self.data.get('password_hash'))

    # ---------- Properties & Update ----------

    def update_base_info(self, age: int, gender: str, weight: float):
        self.data['base_info'] = {
            'age': age,
            'gender': gender,
            'weight': weight,
            'recommended_daily_intake': weight * 0.033
        }
        self.save()

    def set_location(self, location: str):
        self.data['location'] = location
        self.save()

    def set_coords(self, latitude: float, longitude: float):
        """Store GPS coordinates sent from the browser. Updated only on page open."""
        self.data['coords'] = {
            'latitude': latitude,
            'longitude': longitude,
            'updated_at': datetime.now().isoformat()
        }
        self.save()

    def get_coords(self):
        """Return stored GPS coords dict or None."""
        return self.data.get('coords')

    def update_mac_id(self, mac_id: str):
        self.data['mac_id'] = mac_id.upper().strip()
        self.save()

    # ---------- Activity Tracking ----------

    def add_activity_reading(self, value: float):
        """Store a new numeric activity reading from the device."""
        self.data['activity_history'].append({
            'timestamp': datetime.now().isoformat(),
            'value': value
        })
        # Keep only last 30 days of raw readings to prevent unbounded growth
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        self.data['activity_history'] = [
            r for r in self.data['activity_history'] 
            if r['timestamp'] >= cutoff
        ]
        self.save()

    def get_7day_activity_average(self) -> float:
        """Calculate the average activity value over the last 7 days."""
        if not self.data['activity_history']:
            return None
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        recent = [r['value'] for r in self.data['activity_history'] if r['timestamp'] >= cutoff]
        # If we don't yet have a full 7 days of readings, use baseline average
        has_full_week = any(r['timestamp'] < cutoff for r in self.data['activity_history'])
        if not has_full_week:
            return float(config.ACTIVITY_BASELINE_AVG)
        if not recent:
            return float(config.ACTIVITY_BASELINE_AVG)
        return round(sum(recent) / len(recent), 2)

    def get_activity_category(self, current_value: float = None) -> str:
        """
        Categorize activity as Low / Moderate / High.
        Compares current value against the 7-day rolling average.
        During the first 7 days the baseline avg of config.ACTIVITY_BASELINE_AVG (72)
        is used so a category is always returned — never None.
        """
        if current_value is None:
            # Use latest reading if available
            if self.data['activity_history']:
                current_value = self.data['activity_history'][-1]['value']
            else:
                # No readings at all yet — default to Low
                return 'Low'

        avg = self.get_7day_activity_average()
        if avg is None:
            # Truly no history — compare against baseline directly
            avg = float(config.ACTIVITY_BASELINE_AVG)

        ratio = current_value / avg if avg > 0 else 1.0
        if ratio < 0.8:
            return 'Low'
        elif ratio > 1.2:
            return 'High'
        else:
            return 'Moderate'

    # ---------- Water Logging ----------

    def log_water(self, amount: float):
        """Log a water intake event (amount in liters)."""
        self.data['water_log'].append({
            'timestamp': datetime.now().isoformat(),
            'amount': amount
        })
        self.save()

    def get_today_water_intake(self) -> float:
        """Sum of water logged today."""
        today = datetime.now().date().isoformat()
        total = 0.0
        for entry in self.data['water_log']:
            entry_date = entry['timestamp'][:10]  # YYYY-MM-DD
            if entry_date == today:
                total += entry['amount']
        return round(total, 2)

    def get_recommended_intake(self) -> float:
        """Base recommended intake in liters (weight * 0.033)."""
        return self.data['base_info'].get('recommended_daily_intake', 2.0)

    # ---------- Weather History ----------

    def add_weather_reading(self, temperature: float, condition: str, humidity: int = None):
        """Store an hourly weather reading."""
        if 'weather_history' not in self.data:
            self.data['weather_history'] = []
        self.data['weather_history'].append({
            'timestamp': datetime.now().isoformat(),
            'temperature': temperature,
            'condition': condition,
            'humidity': humidity
        })
        # Keep only last 48 hours of readings
        cutoff = (datetime.now() - timedelta(hours=48)).isoformat()
        self.data['weather_history'] = [
            r for r in self.data['weather_history']
            if r['timestamp'] >= cutoff
        ]
        self.save()

    def get_weather_history(self, hours: int = 24) -> list:
        """Return weather readings for the last N hours."""
        if 'weather_history' not in self.data:
            return []
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        return [r for r in self.data['weather_history'] if r['timestamp'] >= cutoff]

    # ---------- Raw Activity Values ----------

    def get_raw_activity_values(self, count: int = 10) -> list:
        """Return the most recent raw activity readings from the device, limited to max 10."""
        return self.data.get('activity_history', [])[-count:]

    # ---------- Legacy methods (keep for Streamlit compat) ----------

    def add_daily_record(self, water_intake, activity_level, weather, felt_dehydrated=False):
        record = {
            'date': datetime.now().date().isoformat(),
            'water_intake': water_intake,
            'activity_level': activity_level,
            'weather': weather,
            'felt_dehydrated': felt_dehydrated,
            'intake_ratio': water_intake / self.data['base_info'].get('recommended_daily_intake', 2.0)
        }

        today = datetime.now().date().isoformat()
        existing = [r for r in self.data['daily_records'] if r['date'] == today]
        if existing:
            idx = self.data['daily_records'].index(existing[0])
            self.data['daily_records'][idx] = record
        else:
            self.data['daily_records'].append(record)

        self.save()

        if len(self.data['daily_records']) >= 5 and not self.data['personalization']['is_calibrated']:
            self._calibrate()

        return len(self.data['daily_records'])

    def _calibrate(self):
        records = self.data['daily_records'][-6:]

        avg_intake_ratio = np.mean([r['intake_ratio'] for r in records])
        dehydration_rate = np.mean([1 if r['felt_dehydrated'] else 0 for r in records])

        if avg_intake_ratio < 0.8 and dehydration_rate < 0.2:
            adjustment = -0.2
        elif avg_intake_ratio >= 0.9 and dehydration_rate > 0.3:
            adjustment = 0.3
        elif dehydration_rate > 0.4:
            adjustment = 0.4
        else:
            adjustment = 0

        self.data['personalization'] = {
            'risk_adjustment': adjustment,
            'is_calibrated': True,
            'calibration_date': datetime.now().isoformat(),
            'avg_intake_ratio': avg_intake_ratio,
            'dehydration_rate': dehydration_rate,
            'total_days_tracked': len(self.data['daily_records'])
        }

        self.save()

    def get_risk_adjustment(self):
        if self.data['personalization']['is_calibrated']:
            return self.data['personalization']['risk_adjustment']
        return 0

    def is_calibrated(self):
        return self.data['personalization']['is_calibrated']

    def get_days_until_calibration(self):
        current_days = len(self.data['daily_records'])
        return max(0, 5 - current_days)

    def get_summary(self):
        base = self.data['base_info']
        pers = self.data['personalization']

        return {
            'user_id': self.user_id,
            'mac_id': self.data.get('mac_id', ''),
            'age': base.get('age'),
            'gender': base.get('gender'),
            'weight': base.get('weight'),
            'location': self.data.get('location', ''),
            'coords': self.data.get('coords'),
            'recommended_daily_intake': base.get('recommended_daily_intake'),
            'today_water_intake': self.get_today_water_intake(),
            'activity_category': self.get_activity_category(),
            'activity_7day_avg': self.get_7day_activity_average(),
            'days_tracked': len(self.data['daily_records']),
            'is_calibrated': pers['is_calibrated'],
            'days_until_calibration': self.get_days_until_calibration(),
            'risk_adjustment': pers['risk_adjustment']
        }
