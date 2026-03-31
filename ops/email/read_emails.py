from pathlib import Path
import subprocess

OUTPUT_FILE = Path("/root/.openclaw/workspace/data/email/email_inbox_snapshot.txt")

def run_command(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print("Command failed:")
        print(result.stderr)
        return None
    return result.stdout

def main():
    cmd = 'gog email search "in:inbox is:unread" --account=sneha.primeidea@gmail.com --limit=10'
    output = run_command(cmd)

    if output is None:
        return

    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"Saved inbox snapshot to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
