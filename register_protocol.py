import winreg
import os
import sys

def register():
    gui_path = os.path.abspath("idm_gui.py")
    cmd_str = f'pythonw "{gui_path}" "%1"'

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\pyidm")
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:PyIDM Protocol")
    winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

    cmd_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\pyidm\shell\open\command")
    winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)
    print("[+] Protocol pyidm:// registered successfully to:", cmd_str)

if __name__ == "__main__":
    register()

