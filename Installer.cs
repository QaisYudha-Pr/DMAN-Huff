using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Runtime.InteropServices;

namespace PyIDMInstaller
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string currentDir = AppDomain.CurrentDomain.BaseDirectory;
            string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string installDir = Path.Combine(localAppData, "Programs", "PyIDM");

            DialogResult res = MessageBox.Show(
                "Welcome to PyIDM Setup!\n\nThis will install PyIDM (Internet Download Manager) to:\n" + installDir + 
                "\n\n- Create Desktop Shortcut\n- Create Start Menu Shortcut\n- Register Browser & Windows Integration\n- Add idm.exe to PATH\n\nDo you want to proceed?",
                "PyIDM Setup",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information
            );

            if (res != DialogResult.Yes)
                return;

            try
            {
                // 1. Create Destination Directory
                Directory.CreateDirectory(installDir);

                // 2. Copy Executables and Folders
                string[] sourceCandidates = new string[] {
                    Path.Combine(currentDir, "dist"),
                    currentDir
                };

                // Copy PyIDM.exe and idm.exe
                foreach (string candidate in sourceCandidates)
                {
                    string pExe = Path.Combine(candidate, "PyIDM.exe");
                    if (File.Exists(pExe))
                    {
                        File.Copy(pExe, Path.Combine(installDir, "PyIDM.exe"), true);
                    }
                    string iExe = Path.Combine(candidate, "idm.exe");
                    if (File.Exists(iExe))
                    {
                        File.Copy(iExe, Path.Combine(installDir, "idm.exe"), true);
                    }
                }

                // Copy browser extension folder
                string srcExt = Path.Combine(currentDir, "browser_extension");
                if (Directory.Exists(srcExt))
                {
                    string dstExt = Path.Combine(installDir, "browser_extension");
                    CopyDirectory(srcExt, dstExt);
                }

                // Copy config.json
                string cfg = Path.Combine(currentDir, "config.json");
                if (File.Exists(cfg))
                {
                    File.Copy(cfg, Path.Combine(installDir, "config.json"), true);
                }

                // Copy Uninstall.exe if exists
                string uninst = Path.Combine(currentDir, "Uninstall.exe");
                if (File.Exists(uninst))
                {
                    File.Copy(uninst, Path.Combine(installDir, "Uninstall.exe"), true);
                }

                // 3. Create Shortcuts
                string pyidmExe = Path.Combine(installDir, "PyIDM.exe");
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string startMenu = Environment.GetFolderPath(Environment.SpecialFolder.Programs);

                CreateShortcut(pyidmExe, Path.Combine(desktop, "PyIDM.lnk"), "PyIDM - Internet Download Manager");
                CreateShortcut(pyidmExe, Path.Combine(startMenu, "PyIDM.lnk"), "PyIDM - Internet Download Manager");

                // 4. Register Protocol pyidm://
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Classes\pyidm"))
                {
                    key.SetValue("", "URL:PyIDM Protocol");
                    key.SetValue("URL Protocol", "");
                    using (RegistryKey cmdKey = key.CreateSubKey(@"shell\open\command"))
                    {
                        cmdKey.SetValue("", "\"" + pyidmExe + "\" \"%1\"");
                    }
                }

                // 5. Register in Windows Programs & Features (Add/Remove Programs)
                using (RegistryKey appKey = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PyIDM"))
                {
                    appKey.SetValue("DisplayName", "PyIDM - Internet Download Manager");
                    appKey.SetValue("DisplayVersion", "1.0.0");
                    appKey.SetValue("Publisher", "Personal IDM");
                    appKey.SetValue("DisplayIcon", pyidmExe);
                    appKey.SetValue("InstallLocation", installDir);
                    appKey.SetValue("UninstallString", "\"" + Path.Combine(installDir, "Uninstall.exe") + "\"");
                }

                // 6. Add to User PATH
                string userPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? "";
                if (!userPath.Contains(installDir))
                {
                    Environment.SetEnvironmentVariable("Path", userPath + ";" + installDir, EnvironmentVariableTarget.User);
                }

                DialogResult launch = MessageBox.Show(
                    "Installation completed successfully!\n\nPyIDM is now installed.\nDesktop and Start Menu shortcuts were created.\n'idm' command is available in terminal.\n\nWould you like to launch PyIDM now?",
                    "PyIDM Installed",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Information
                );

                if (launch == DialogResult.Yes && File.Exists(pyidmExe))
                {
                    Process.Start(pyidmExe);
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Installation failed:\n" + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static void CopyDirectory(string sourceDir, string targetDir)
        {
            Directory.CreateDirectory(targetDir);
            foreach (var file in Directory.GetFiles(sourceDir))
                File.Copy(file, Path.Combine(targetDir, Path.GetFileName(file)), true);
            foreach (var sub in Directory.GetDirectories(sourceDir))
                CopyDirectory(sub, Path.Combine(targetDir, Path.GetFileName(sub)));
        }

        static void CreateShortcut(string targetPath, string shortcutPath, string description)
        {
            Type t = Type.GetTypeFromCLSID(new Guid("72C24DD5-D70A-438B-8A42-98424B88AFB8")); // WScript.Shell
            dynamic shell = Activator.CreateInstance(t);
            try
            {
                var lnk = shell.CreateShortcut(shortcutPath);
                lnk.TargetPath = targetPath;
                lnk.WorkingDirectory = Path.GetDirectoryName(targetPath);
                lnk.Description = description;
                lnk.Save();
            }
            finally
            {
                Marshal.FinalReleaseComObject(shell);
            }
        }
    }
}

