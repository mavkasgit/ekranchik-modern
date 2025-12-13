"""Migrate data from old profiles.db to new ekranchik.db"""
import sqlite3
import shutil
from pathlib import Path

SOURCE_DB = Path(r'D:\KTM\KTM2000\static\profiles.db')
TARGET_DB = Path(r'D:\KTM\KTM2000\static\ekranchik.db')

def migrate():
    print(f"Source: {SOURCE_DB}")
    print(f"Target: {TARGET_DB}")
    
    if not SOURCE_DB.exists():
        print("ERROR: Source DB not found!")
        return
    
    # Connect to source
    src_conn = sqlite3.connect(SOURCE_DB)
    src_cursor = src_conn.cursor()
    
    # Get all profiles from source
    src_cursor.execute("SELECT * FROM profiles")
    profiles = src_cursor.fetchall()
    print(f"Found {len(profiles)} profiles in source DB")
    
    # Connect to target
    tgt_conn = sqlite3.connect(TARGET_DB)
    tgt_cursor = tgt_conn.cursor()
    
    # Check if profiles table exists
    tgt_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='profiles'")
    if not tgt_cursor.fetchone():
        print("Creating profiles table...")
        tgt_cursor.execute("""
            CREATE TABLE profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                quantity_per_hanger INTEGER,
                length REAL,
                notes TEXT,
                photo_thumb TEXT,
                photo_full TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                usage_count INTEGER DEFAULT 0
            )
        """)
        tgt_cursor.execute("CREATE INDEX idx_profile_name ON profiles(name)")
        tgt_cursor.execute("CREATE INDEX idx_profile_usage ON profiles(usage_count)")
    
    # Check existing count
    tgt_cursor.execute("SELECT COUNT(*) FROM profiles")
    existing = tgt_cursor.fetchone()[0]
    print(f"Existing profiles in target: {existing}")
    
    if existing > 0:
        print("Target DB already has data. Clearing...")
        tgt_cursor.execute("DELETE FROM profiles")
    
    # Insert profiles
    inserted = 0
    for profile in profiles:
        # id, name, quantity_per_hanger, length, notes, photo_thumb, photo_full, created_at, updated_at, usage_count
        try:
            tgt_cursor.execute("""
                INSERT INTO profiles (id, name, quantity_per_hanger, length, notes, photo_thumb, photo_full, created_at, updated_at, usage_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, profile)
            inserted += 1
        except Exception as e:
            print(f"Error inserting {profile[1]}: {e}")
    
    tgt_conn.commit()
    print(f"Inserted {inserted} profiles")
    
    # Verify
    tgt_cursor.execute("SELECT COUNT(*) FROM profiles")
    final_count = tgt_cursor.fetchone()[0]
    print(f"Final count in target: {final_count}")
    
    src_conn.close()
    tgt_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
