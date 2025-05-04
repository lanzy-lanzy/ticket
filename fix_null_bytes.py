# Script to remove null bytes from files
import os

def fix_file(file_path):
    try:
        # Read the file content
        with open(file_path, 'rb') as f:
            content = f.read()
        
        # Remove null bytes
        content = content.replace(b'\x00', b'')
        
        # Write back to the file
        with open(file_path, 'wb') as f:
            f.write(content)
        
        print(f"Fixed file: {file_path}")
        return True
    except Exception as e:
        print(f"Error fixing file {file_path}: {str(e)}")
        return False

# Fix the files
files_to_fix = [
    'trip/urls.py',
    'trip/views.py'
]

for file_path in files_to_fix:
    fix_file(file_path)

print("Done!")
