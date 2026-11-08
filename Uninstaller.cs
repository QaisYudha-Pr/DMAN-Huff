using System;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;

namespace PyIDMUninstaller
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            DialogResult res = MessageBox.Show(
                "Are you sure you want to completely uninstall PyIDM and remove its shortcuts and settings?",
                "Uninstall PyIDM",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Question
            );

            if (res != DialogResult.Yes)
                return;

            try
            {
                string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
                string installDir = Path.Combine(localAppData, "Programs", "PyIDM");

                // 1. Remove Shortcuts
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string startMenu = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
                string deskLnk = Path.Combine(desktop, "PyIDM.lnk");
                string startLnk = Path.Combine(startMenu, "PyIDM.lnk");

                if (File.Exists(deskLnk)) File.Delete(deskLnk);
                if (File.Exists(startLnk)) File.Delete(startLnk);

                // 2. Remove Registry entries
                try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Classes\pyidm", false); } catch {}
                try { Registry.CurrentUser.DeleteSubKeyTree(@"Software\Microsoft\Windows\CurrentVersion\Uninstall\PyIDM", false); } catch {}

                // 3. Clean PATH
                string userPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.User) ?? "";
                if (userPath.Contains(installDir))
                {
                    string newPath = userPath.Replace(";" + installDir, "").Replace(installDir + ";", "").Replace(installDir, "");
                    Environment.SetEnvironmentVariable("Path", newPath, EnvironmentVariableTarget.User);
                }

                // 4. Remove installation files
                if (Directory.Exists(installDir))
                {
                    // Self-deletion of uninstaller directory via cmd timeout
                    string cmd = string.Format("/c timeout /t 1 /nobreak & rmdir /s /q \"{0}\"", installDir);
                    System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo()
                    {
                        FileName = "cmd.exe",
                        Arguments = cmd,
                        WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
                        CreateNoWindow = true
                    });
                }

                MessageBox.Show("PyIDM has been successfully uninstalled from your computer.", "Uninstalled", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Uninstall error: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }
}

