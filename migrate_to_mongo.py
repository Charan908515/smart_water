import json
import os
import glob
from database import get_db

def migrate():
    db = get_db()
    if db is None:
        print("MongoDB not connected. Exiting.")
        return

    users_col = db.users
    profiles_dir = "user_profiles"
    if not os.path.exists(profiles_dir):
        print("No user_profiles directory found.")
        return

    count = 0
    for filepath in glob.glob(os.path.join(profiles_dir, "*.json")):
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            mac_id = data.get('mac_id')
            if not mac_id:
                print(f"Skipping {filepath}: No mac_id found.")
                continue

            # Upsert into MongoDB
            users_col.update_one(
                {'mac_id': mac_id},
                {'$set': data},
                upsert=True
            )
            count += 1
            print(f"Migrated user {mac_id}")
        except Exception as e:
            print(f"Error migrating {filepath}: {e}")

    print(f"Migration complete. Migrated {count} users.")

if __name__ == "__main__":
    migrate()
