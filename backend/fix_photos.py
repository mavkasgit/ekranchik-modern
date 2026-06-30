import sqlite3
import os
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Paths
db_path = r"c:\Users\user\VibeCoding\ekranchik-modern\static\ekranchik.db"
images_dir = r"c:\Users\user\VibeCoding\ekranchik-modern\static\images"

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    sys.exit(1)
if not os.path.exists(images_dir):
    print(f"Error: Images directory not found at {images_dir}")
    sys.exit(1)

print("Starting photo database and files fix...")
print("=" * 60)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Update paths in Database
cursor.execute("SELECT id, name, photo_thumb, photo_full FROM profiles")
rows = cursor.fetchall()

db_updates = 0
for row in rows:
    pid, name, thumb, full = row
    new_thumb = thumb
    new_full = full
    
    if thumb and thumb.startswith('/static/'):
        new_thumb = thumb.replace('/static/', '')
    elif thumb and thumb.startswith('static/'):
        new_thumb = thumb.replace('static/', '')
        
    if full and full.startswith('/static/'):
        new_full = full.replace('/static/', '')
    elif full and full.startswith('static/'):
        new_full = full.replace('static/', '')
        
    if new_thumb != thumb or new_full != full:
        cursor.execute(
            "UPDATE profiles SET photo_thumb = ?, photo_full = ? WHERE id = ?",
            (new_thumb, new_full, pid)
        )
        db_updates += 1
        print(f"Updated DB paths for [{name}] (ID: {pid}):")
        print(f"  thumb: {thumb} -> {new_thumb}")
        print(f"  full:  {full} -> {new_full}")

conn.commit()
print(f"-> Successfully updated {db_updates} profiles in Database.")
print("-" * 60)

# 2. Fix flipped files on disk
# Fetch updated rows
cursor.execute("SELECT id, name, photo_thumb, photo_full FROM profiles")
rows = cursor.fetchall()

flipped_files_fixed = 0

for row in rows:
    pid, name, thumb, full = row
    
    if not thumb or not full:
        continue
        
    # Get filenames relative to images directory
    # DB paths are 'images/{filename}.jpg'
    thumb_filename = os.path.basename(thumb)
    full_filename = os.path.basename(full)
    
    thumb_path = os.path.join(images_dir, thumb_filename)
    full_path = os.path.join(images_dir, full_filename)
    
    if os.path.exists(thumb_path) and os.path.exists(full_path):
        thumb_size = os.path.getsize(thumb_path)
        full_size = os.path.getsize(full_path)
        
        # If thumbnail size is greater than full size, they are swapped!
        if thumb_size > full_size:
            print(f"Swapping flipped images for [{name}] (ID: {pid}):")
            print(f"  {thumb_filename} ({thumb_size} bytes) <-> {full_filename} ({full_size} bytes)")
            
            temp_path = os.path.join(images_dir, "temp_swap.jpg")
            
            try:
                # Perform swap
                os.rename(full_path, temp_path)
                os.rename(thumb_path, full_path)
                os.rename(temp_path, thumb_path)
                flipped_files_fixed += 1
                print("  -> Swapped successfully!")
            except Exception as e:
                print(f"  -> Error during swap: {e}")
                if os.path.exists(temp_path):
                    try:
                        os.rename(temp_path, full_path)
                    except:
                        pass

conn.close()

print("=" * 60)
print("Migration completed!")
print(f"Total database profiles updated: {db_updates}")
print(f"Total flipped image file pairs swapped: {flipped_files_fixed}")
