#!/usr/bin/env python3
"""
Script to replace YouTube detection section in final_working_bot.py
"""

# Read the original file
with open('final_working_bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Read the patch
with open('message_handler_patch.py', 'r', encoding='utf-8') as f:
    patch_content = f.read()

# Remove the first comment line from patch
patch_lines = [line for line in patch_content.split('\n') if not line.strip().startswith('# Message Handler')]
patch_text = '\n'.join(patch_lines[1:])  # Skip first 2 lines (comments)

# Find the section to replace (line 3992 to 4026 - 0-indexed: 3991 to 4025)
# We need to replace from "if youtube_links:" to the line before "else:"
start_idx = 3991  # Line 3992 in 1-indexed
end_idx = 4025    # Line 4026 in 1-indexed

# Build new file
new_lines = lines[:start_idx] + [patch_text + '\n'] + lines[end_idx:]

# Write modified file
with open('final_working_bot.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("✅ Message handler patched successfully!")
print(f"   Replaced lines {start_idx+1} to {end_idx+1}")
