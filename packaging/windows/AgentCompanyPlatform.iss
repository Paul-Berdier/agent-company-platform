; Installeur Windows d'Agent Company Platform (Inno Setup 6.4 ou plus récent).
;
; Ce script n'est jamais compilé à la main : scripts/package-desktop.ps1 l'appelle
; en lui passant les quatre définitions ci-dessous. Compilé sans elles, ISCC refuse.
;
;   AcpVersion             version du produit, lue dans le fichier VERSION
;   AcpSourceDir           répertoire déjà déployé par windeployqt (contenu de l'installation)
;   AcpOutputDir           répertoire où écrire le programme d'installation
;   AcpOutputBaseFilename  nom de l'artefact, sans l'extension .exe
;
; Installation par utilisateur : PrivilegesRequired=lowest, donc aucune élévation
; demandée et aucune invite de contrôle de compte d'utilisateur au lancement.
; {autopf} se résout alors en {userpf}, c'est-à-dire %LOCALAPPDATA%\Programs.
; Un administrateur qui veut une installation pour toute la machine passe /ALLUSERS
; en ligne de commande, ce que PrivilegesRequiredOverridesAllowed=commandline autorise.
; Référence : https://jrsoftware.org/ishelp/ (directives PrivilegesRequired,
; PrivilegesRequiredOverridesAllowed et constantes {auto*}), consultée le 18 septembre 2026.

#ifndef AcpVersion
  #error AcpVersion n'est pas defini. Utilisez scripts/package-desktop.ps1.
#endif
#ifndef AcpSourceDir
  #error AcpSourceDir n'est pas defini. Utilisez scripts/package-desktop.ps1.
#endif
#ifndef AcpOutputDir
  #error AcpOutputDir n'est pas defini. Utilisez scripts/package-desktop.ps1.
#endif
#ifndef AcpOutputBaseFilename
  #error AcpOutputBaseFilename n'est pas defini. Utilisez scripts/package-desktop.ps1.
#endif

#define AcpName "Agent Company Platform"
#define AcpPublisher "Agent Company Platform"
#define AcpExeName "AgentCompanyPlatform.exe"

[Setup]
; AppId identifie l'application pour la mise à jour sur place et pour l'entrée de
; désinstallation de Windows. Il ne change jamais : le modifier ferait apparaître
; deux entrées de désinstallation sur les postes déjà équipés.
AppId={{53810A6E-FA9C-4595-9C53-74A78EB4D1A8}
AppName={#AcpName}
AppVersion={#AcpVersion}
AppVerName={#AcpName} {#AcpVersion}
VersionInfoVersion={#AcpVersion}
AppPublisher={#AcpPublisher}
DefaultDirName={autopf}\{#AcpName}
DefaultGroupName={#AcpName}
DisableProgramGroupPage=yes
UninstallDisplayName={#AcpName}
UninstallDisplayIcon={app}\{#AcpExeName}
OutputDir={#AcpOutputDir}
OutputBaseFilename={#AcpOutputBaseFilename}
SourceDir={#AcpSourceDir}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
AllowNoIcons=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Le contenu est celui produit par windeployqt : l'exécutable, les bibliothèques Qt
; dont il dépend réellement, les greffons et les modules QML détectés par analyse du
; répertoire QML source. Rien n'est ajouté à la main ici.
Source: "*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AcpName}"; Filename: "{app}\{#AcpExeName}"
Name: "{autodesktop}\{#AcpName}"; Filename: "{app}\{#AcpExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AcpExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AcpName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Supprime ce que l'application a pu écrire dans son propre répertoire d'installation
; (caches QML notamment). La configuration de l'utilisateur vit ailleurs, sous
; %APPDATA%, et n'est volontairement PAS supprimée : réinstaller ne fait pas perdre
; l'URL du serveur ni les préférences d'affichage.
Type: filesandordirs; Name: "{app}"
