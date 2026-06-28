import pexpect
import sys

def main():
    print("Starting gh auth login...")
    child = pexpect.spawn(".venv/bin/gh auth login", encoding="utf-8")
    child.logfile_read = sys.stdout
    
    child.expect("What account do you want to log into")
    child.sendline("")
    
    child.expect("What is your preferred protocol")
    child.sendline("")
    
    child.expect("Authenticate Git with your GitHub credentials")
    child.sendline("Y") 
    
    child.expect("How would you like to authenticate")
    child.sendline("") 
    
    child.expect("First copy your one-time code:")
    
    print("\n=== WAITING FOR BROWSER AUTH ===")
    child.interact()

if __name__ == "__main__":
    main()
