using System;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;
using System.Reflection;

[assembly: AssemblyTitle("Dmans Uninstaller")]
[assembly: AssemblyDescription("Uninstaller for Dmans Download Accelerator")]
[assembly: AssemblyCompany("Dmans Open Source Project")]
[assembly: AssemblyProduct("Dmans Download Accelerator")]
[assembly: AssemblyCopyright("Copyright © 2026 Dmans Contributors")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace DmansUninstaller
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            DialogResult res = MessageBox.Show(
                "Are you sure you want to completely uninstall Dmans and remove its shortcuts and settings?",
                "Uninstall Dmans",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            );

            if (res != DialogResult.Yes)
                return;

            try
            {
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string installDir = Path.Combine(localAppData, "Programs", "Dmans");

                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string startMenu = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                string deskLnk = Path.Combine(desktop, "Dmans.lnk");
                string startLnk = Path.Combine(startMenu, "Dmans.lnk");

                if (File.Exists(deskLnk)) File.Delete(deskLnk);
                if (File.Exists(startLnk)) File.Delete(startLnk);

                try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\dmans", false); } catch {}
                try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\Dmans", false); } catch {}

                string userPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? "";
                if (userPath.Contains(installDir))
                {
                    string newPath = userPath.Replace(";" + installDir, "").Replace(installDir + ";", "").Replace(installDir, "");
                    Environment.SetEnvironmentVariable("Path", newPath, EnvironmentVariableTarget.User);
                }

                // Delete installed files (except uninstaller itself if running from installDir)
                if (Directory.Exists(installDir))
                {
                    foreach (var file in Directory.GetFiles(installDir))
                    {
                        try
                        {
                            if (!file.EndsWith("Uninstall.exe", StringComparison.OrdinalIgnoreCase))
                                File.Delete(file);
                        }
                        catch {}
                    }
                }

                MessageBox.Show("Dmans has been successfully uninstalled from your computer.", "Uninstalled", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Uninstall error: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}
