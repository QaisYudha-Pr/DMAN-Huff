using System;
using System.IO;
using System.Diagnostics;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Runtime.InteropServices;
using System.Reflection;

[assembly: AssemblyTitle("Dmans Setup")]
[assembly: AssemblyDescription("Installer for Dmans Download Accelerator")]
[assembly: AssemblyCompany("Dmans Open Source Project")]
[assembly: AssemblyProduct("Dmans Download Accelerator")]
[assembly: AssemblyCopyright("Copyright © 2026 Dmans Contributors")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace DmansInstaller
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
            string installDir = Path.Combine(localAppData, "Programs", "Dmans");

            DialogResult res = MessageBox.Show(
                "Welcome to Dmans Setup!\n\nThis will install Dmans (Fast Download Accelerator) to:\n" + installDir + 
                "\n\nFeatures:\n- Desktop Shortcut\n- Start Menu Shortcut\n- Global 'dmans' Command in Terminal\n- Browser Extension & URL Protocol Support\n\nDo you want to proceed?",
                "Dmans Setup",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Information
            );

            if (res != DialogResult.Yes)
                return;

            try
            {
                Directory.CreateDirectory(installDir);

                string[] binaries = new string[] { "Dmans.exe", "dmans-cli.exe", "Uninstall.exe", "config.json" };
                foreach (string b in binaries)
                {
                    string src = Path.Combine(currentDir, b);
                    if (File.Exists(src))
                    {
                        File.Copy(src, Path.Combine(installDir, b), true);
                    }
                }
                string cliSrc = Path.Combine(installDir, "dmans-cli.exe");
                if (File.Exists(cliSrc))
                {
                    File.Copy(cliSrc, Path.Combine(installDir, "dmans.exe"), true);
                }

                string srcExt = Path.Combine(currentDir, "browser_extension");
                if (Directory.Exists(srcExt))
                {
                    string dstExt = Path.Combine(installDir, "browser_extension");
                    CopyDirectory(srcExt, dstExt);
                }

                string dmansExe = Path.Combine(installDir, "Dmans.exe");
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string startMenu = Environment.GetFolderPath(Environment.SpecialFolder.Programs);

                CreateShortcut(dmansExe, Path.Combine(desktop, "Dmans.lnk"), "Dmans - Fast Download Accelerator");
                CreateShortcut(dmansExe, Path.Combine(startMenu, "Dmans.lnk"), "Dmans - Fast Download Accelerator");

                // Register dmans:// protocol
                using (RegistryKey key = Registry.CurrentUser.CreateSubKey(@"Software\Classes\dmans"))
                {
                    key.SetValue("", "URL:Dmans Protocol");
                    key.SetValue("URL Protocol", "");
                    using (RegistryKey cmdKey = key.CreateSubKey(@"shell\open\command"))
                    {
                        cmdKey.SetValue("", "\"" + dmansExe + "\" \"%1\"");
                    }
                }

                // Register Windows Programs & Features
                using (RegistryKey appKey = Registry.CurrentUser.CreateSubKey(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\Dmans"))
                {
                    appKey.SetValue("DisplayName", "Dmans - Download Accelerator");
                    appKey.SetValue("DisplayVersion", "1.0.0");
                    appKey.SetValue("Publisher", "Dmans Open Source Project");
                    appKey.SetValue("DisplayIcon", dmansExe);
                    appKey.SetValue("InstallLocation", installDir);
                    appKey.SetValue("UninstallString", "\"" + Path.Combine(installDir, "Uninstall.exe") + "\"");
                }

                // Add to User PATH
                string userPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? "";
                if (!userPath.Contains(installDir))
                {
                    Environment.SetEnvironmentVariable("Path", userPath + ";" + installDir, EnvironmentVariableTarget.User);
                }

                DialogResult launch = MessageBox.Show(
                    "Installation completed successfully!\n\nShortcuts have been created on your Desktop and Start Menu.\n'dmans' is now available in any terminal.\n\nWould you like to launch Dmans now?",
                    "Dmans Installed",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Information
                );

                if (launch == DialogResult.Yes && File.Exists(dmansExe))
                {
                    Process.Start(dmansExe);
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
            Type t = Type.GetTypeFromCLSID(new Guid("72C24DD5-D70A-438B-8A42-98424B88AFB8"));
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
