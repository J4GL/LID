const STORAGE_KEY = "p2p-language";

const messages = {
  en: {
    "app.title": "LID — Linux ISO Downloader",
    "app.home": "LID, home",
    "language.toggle": "Switch language to French",
    "header.tagline": "Linux ISO Downloader",
    "header.proxy": "Proxy status",
    dashboard: "DASHBOARD",
    transfers: "Transfers",
    "add.open": "Add a torrent",
    "metrics.activity": "Global activity",
    "metrics.download": "Download",
    "metrics.download_note": "Download speed",
    "metrics.upload": "Upload",
    "metrics.upload_note": "Sharing speed",
    "metrics.seeding": "Seeding",
    "metrics.seeding_note": "Continuous seeding with no ratio limit",
    "metrics.ratio": "Global ratio",
    "metrics.ratio_note": "Total uploaded / downloaded",
    "list.title": "My torrents",
    "list.direct": "Direct",
    "list.proxy": "Proxy",
    "list.aria": "Torrent list",
    "list.torrent": "TORRENT",
    "list.progress": "PROGRESS",
    "list.transfer": "DOWNLOAD / UPLOAD",
    "list.actions": "ACTIONS",
    "empty.title": "Room for your next torrents.",
    "empty.text": "Drop a file here, then choose its route.",
    "empty.left": "Left for direct",
    "empty.right": "Right through proxy",
    "empty.add": "or add a file / magnet link",
    "footer.connecting": "Connecting to the application…",
    "footer.live": "Live and up to date",
    "footer.reconnecting": "Reconnecting…",
    "footer.unavailable": "Server unavailable",
    "footer.setup": "Configuration required",
    "footer.tagline": "Two routes. One space.",
    "folders.open": "Folders ↗",
    "settings.open": "Settings ↗",
    "settings.eyebrow": "CONFIGURATION",
    "settings.title": "LID settings.",
    "settings.welcome": "Welcome to LID.",
    "settings.setup_note":
      "Torrent engines stay stopped until this configuration is saved.",
    "settings.steps_aria": "Configuration steps",
    "settings.step_storage": "Storage",
    "settings.step_connections": "Connections",
    "settings.step_performance": "Performance",
    "settings.storage_title": "Storage",
    "settings.storage_help":
      "Choose folders on the machine running LID. They must be separate and cannot be symbolic links.",
    "settings.state_folder": "Internal LID data",
    "settings.state_help":
      "Changing this folder restarts LID and safely moves resume data and indexes.",
    "settings.connections_title": "Connections",
    "settings.web_host": "Web listen address",
    "settings.web_port": "Web port",
    "settings.direct_port": "Direct TCP / UDP port",
    "settings.upnp": "Enable UPnP for direct transfers",
    "settings.proxy_enabled": "Enable SOCKS5 proxy mode",
    "settings.proxy_host": "Proxy host",
    "settings.proxy_port": "Proxy port",
    "settings.proxy_username": "Username",
    "settings.proxy_password": "Password",
    "settings.password_keep": "Leave blank to keep the saved password",
    "settings.clear_password": "Delete saved password",
    "settings.proxy_udp": "UDP through proxy",
    "settings.udp_auto": "Automatic, TCP fallback",
    "settings.udp_off": "Disabled",
    "settings.test_proxy": "Test proxy",
    "settings.testing_proxy": "Testing the proxy…",
    "settings.proxy_tcp_udp_ok": "Proxy works over TCP and its UDP round trip is validated.",
    "settings.proxy_tcp_ok": "Proxy works over TCP. UDP is unavailable; proxy torrents will use TCP only.",
    "settings.proxy_failed": "The proxy is unreachable. You can save, but proxy downloads will remain blocked.",
    "settings.advanced": "Advanced",
    "settings.timeout": "Proxy timeout (seconds)",
    "settings.check_interval": "Health check interval (seconds)",
    "settings.dns_server": "Remote DNS server",
    "settings.dht_nodes": "DHT bootstrap nodes (one host:port per line)",
    "settings.performance_title": "Performance and review",
    "settings.performance_help": "Limits are in bytes per second. Use 0 for unlimited bandwidth.",
    "settings.upload_limit": "Upload limit (B/s)",
    "settings.download_limit": "Download limit (B/s)",
    "settings.connections": "Connection limit",
    "settings.file_pool": "Open file pool",
    "settings.save_interval": "Resume save interval (seconds)",
    "settings.previous": "Previous",
    "settings.next": "Next",
    "settings.save": "Save settings",
    "settings.saving": "Saving…",
    "settings.disabled": "disabled",
    "settings.no_completed": "no automatic move",
    "settings.review": "Web: {host}:{port} · Downloads: {downloads} · Completed: {completed} · Proxy: {proxy}",
    "settings.restarting": "LID is restarting…",
    "settings.restarting_help": "This page will reconnect automatically.",
    "drop.direct_title": "Download directly",
    "drop.direct_text": "Uses your Internet connection.",
    "drop.left": "Drop on the left",
    "drop.proxy_title": "Download through proxy",
    "drop.proxy_text": "Transfer exclusively through the proxy.",
    "drop.right": "Drop on the right",
    "drop.hint": ".torrent · Release the file in the route you want",
    "add.eyebrow": "NEW TRANSFER",
    "add.title": "Choose a route.",
    "add.close": "Close",
    "add.mode_aria": "Transfer mode",
    "add.direct_note": "Your Internet connection",
    "add.mode_help": "The route is preserved during download and seeding.",
    "add.files": "Choose .torrent files",
    "add.or_magnet": "OR A MAGNET LINK",
    "add.magnet_label": "Magnet link",
    "add.magnet": "Add link",
    "folders.eyebrow": "STORAGE",
    "folders.title": "Your folders.",
    "folders.incoming": "Downloads in progress",
    "folders.completed": "Completed downloads",
    "folders.completed_placeholder":
      "Choose a folder on this disk or another one",
    "folders.browse": "Browse",
    "folders.browse_incoming": " the downloads-in-progress folder",
    "folders.browse_completed": " the completed-downloads folder",
    "folders.move": "Move completed downloads",
    "folders.help_move":
      "Existing completed files stay where they are. Active transfers keep their current folder, then move when complete. Seeding continues from the destination.",
    "folders.help_machine":
      "These folders are on the machine running the application. Choose existing folders; files are organized by route and torrent.",
    "folders.save": "Save folders",
    "folders.saving": "Saving…",
    "folders.browser_aria": "Folder browser",
    "folders.path_label": "Path to browse",
    "folders.go": "Go",
    "folders.parent": "↑ Parent folder",
    "folders.loading": "Reading folders…",
    "folders.subfolders": "Subfolders",
    "folders.empty": "No accessible subfolders.",
    "folders.more": "Show more",
    "folders.back": "Back",
    "folders.choose": "Choose this folder",
    "folders.shortcut.home": "Home folder",
    "folders.shortcut.root": "Root",
    "folders.shortcut.drives": "Drives",
    "folders.shortcut.media": "Media",
    "folders.shortcut.mounts": "Mounts",
    "folders.shortcut.user_drives": "User drives",
    "proxy.eyebrow": "CONNECTION",
    "proxy.title": "Your proxy.",
    "proxy.checking": "Checking…",
    "proxy.tcp": "TCP traffic",
    "proxy.udp": "UDP relay",
    "proxy.last_check": "Last check",
    "proxy.audit": "Leak audit",
    "proxy.not_certified": "Not certified",
    "proxy.note":
      "The connection test checks access to the proxy. The network traffic audit is a separate control; this test does not provide an absolute guarantee.",
    "proxy.recheck": "Check connection ↗",
    "proxy.functional": "Working",
    "proxy.unavailable": "Unavailable",
    "proxy.udp_valid": "Round trip validated",
    "proxy.udp_invalid": "Disabled / not validated",
    "proxy.pending": "Pending",
    "proxy.none": "No proxy configured",
    "proxy.not_configured": "Not configured",
    "proxy.short_tcp_udp": "Proxy · TCP + UDP",
    "proxy.short_tcp": "Proxy · TCP",
    "proxy.short_unavailable": "Proxy unavailable",
    "proxy.short_checking": "Checking proxy",
    "proxy.message.proxy_checking": "Checking the proxy…",
    "proxy.message.proxy_active_tcp_udp": "Proxy active — TCP + UDP",
    "proxy.message.proxy_active_tcp": "Proxy active — TCP only",
    "proxy.message.proxy_active_udp_no_dht":
      "Proxy active — UDP available, DHT bootstrap unavailable",
    "proxy.message.proxy_unavailable":
      "Proxy unavailable — proxy downloads are blocked.",
    "proxy.message.proxy_not_configured":
      "No proxy configured: download blocked. Configure the proxy in config.yaml.",
    "state.waiting": "Waiting",
    "state.checking": "Checking",
    "state.metadata": "Metadata",
    "state.downloading": "Downloading",
    "state.finished": "Finished",
    "state.seeding": "Seeding",
    "state.allocating": "Allocating",
    "state.error": "Error",
    "state.paused": "Paused",
    "state.proxy_blocked": "Proxy blocked",
    "state.moving": "Moving files",
    "state.move_verifying": "Checking after move",
    "state.move_pending": "Move pending",
    "state.storage_unavailable": "Storage unavailable",
    "state.engine_stopped": "Engine stopped",
    "torrent.peer_one": "peer",
    "torrent.peer_many": "peers",
    "torrent.ratio": "Ratio {value}",
    "torrent.volumes": "Downloaded {downloaded} · Uploaded {uploaded}",
    "torrent.last_upload": "Last upload: {value}",
    "torrent.destination": "Destination: {path}",
    "torrent.progress": "Progress for {name}",
    "torrent.resume": "Resume",
    "torrent.pause": "Pause",
    "torrent.remove": "Remove torrent and keep files",
    "torrent.retry_move": "Retry move",
    "torrent.unit_one": "torrent",
    "torrent.unit_many": "torrents",
    "toast.close": "Close message",
    "toast.retry_move": "Move retry requested.",
    "toast.removed": "Torrent removed. Files were kept.",
    "toast.busy": "Another torrent is already being added.",
    "toast.added": "{name} added through {mode}.",
    "toast.magnet_added": "Magnet link added.",
    "toast.proxy_check": "Checking proxy connection…",
    "toast.folders_saved": "Folders saved and applied to both engines.",
    "toast.settings_saved": "Settings saved and applied to both engines.",
    "connection.interrupted":
      "The server connection was interrupted. Transfers continue in the background engines.",
    "error.unexpected_response": "Unexpected response from the server.",
    "error.invalid_request":
      "Invalid request. Check the fields and selected route.",
    "error.pending_storage":
      "Settings were saved but have not reached both engines yet. Save them again or restart.",
    "error.session_expired": "Session expired. Reload the page.",
    "error.proxy_not_configured":
      "No proxy configured: download blocked. Configure the proxy in config.yaml.",
    "error.proxy_unavailable":
      "Proxy unavailable: proxy downloads are blocked.",
    "error.too_many_files": "A drop can contain at most 20 files.",
    "error.invalid_file_type": "Only .torrent files are accepted.",
    "error.file_too_large": "The torrent file is too large (10 MiB maximum).",
    "error.torrent_not_found": "Torrent not found.",
    "error.duplicate_torrent": "This torrent has already been added.",
    "error.invalid_torrent": "Invalid torrent or magnet link.",
    "error.engine_unavailable":
      "Torrent engine unavailable. Restart the application.",
    "error.storage_collision":
      "The destination is already occupied. No files were overwritten; free the folder and retry.",
    "error.storage_full":
      "Not enough space on the destination disk. Files remain in their current folder.",
    "error.storage_ambiguous":
      "The interrupted move left files in multiple locations. Gather a complete copy in one location and retry.",
    "error.storage_corrupt":
      "Pieces are missing or corrupt after the move. Recovery is blocked and no data will be downloaded automatically.",
    "error.move_in_progress": "A move is in progress. Wait until it finishes.",
    "error.move_not_retryable": "There is no move to retry for this torrent.",
    "error.move_failed":
      "The move failed. Check the disk and files before retrying.",
    "error.storage_restore_path":
      "The saved storage path is inconsistent. Restore is blocked.",
    "error.storage_unavailable":
      "Storage is unavailable. Check the selected folders, disk and permissions.",
    "error.invalid_path": "The selected path is invalid or unavailable.",
    "error.invalid_settings": "Some settings are invalid. Check the highlighted values.",
    "error.operation_failed": "The operation failed.",
  },
  fr: {
    "app.title": "LID — Linux ISO Downloader",
    "app.home": "LID, accueil",
    "language.toggle": "Passer l’interface en anglais",
    "header.tagline": "Linux ISO Downloader",
    "header.proxy": "État du proxy",
    dashboard: "TABLEAU DE BORD",
    transfers: "Transferts",
    "add.open": "Ajouter un torrent",
    "metrics.activity": "Activité globale",
    "metrics.download": "Réception",
    "metrics.download_note": "Débit de téléchargement",
    "metrics.upload": "Envoi",
    "metrics.upload_note": "Débit de partage",
    "metrics.seeding": "En partage",
    "metrics.seeding_note": "Seeding continu, sans limite de ratio",
    "metrics.ratio": "Ratio global",
    "metrics.ratio_note": "Total envoyé / reçu",
    "list.title": "Mes torrents",
    "list.direct": "Direct",
    "list.proxy": "Proxy",
    "list.aria": "Liste des torrents",
    "list.torrent": "TORRENT",
    "list.progress": "PROGRESSION",
    "list.transfer": "RÉCEPTION / ENVOI",
    "list.actions": "ACTIONS",
    "empty.title": "Une place pour vos prochains torrents.",
    "empty.text": "Glissez un fichier ici, puis choisissez sa route.",
    "empty.left": "À gauche, en direct",
    "empty.right": "À droite, via proxy",
    "empty.add": "ou ajouter un fichier / un lien magnet",
    "footer.connecting": "Connexion à l’application…",
    "footer.live": "À jour en temps réel",
    "footer.reconnecting": "Reconnexion…",
    "footer.unavailable": "Serveur indisponible",
    "footer.setup": "Configuration requise",
    "footer.tagline": "Deux routes. Un seul espace.",
    "folders.open": "Dossiers ↗",
    "settings.open": "Réglages ↗",
    "settings.eyebrow": "CONFIGURATION",
    "settings.title": "Réglages de LID.",
    "settings.welcome": "Bienvenue dans LID.",
    "settings.setup_note":
      "Les moteurs torrent restent arrêtés jusqu’à l’enregistrement de cette configuration.",
    "settings.steps_aria": "Étapes de configuration",
    "settings.step_storage": "Stockage",
    "settings.step_connections": "Connexions",
    "settings.step_performance": "Performances",
    "settings.storage_title": "Stockage",
    "settings.storage_help":
      "Choisissez des dossiers sur la machine qui exécute LID. Ils doivent être séparés et ne peuvent pas être des liens symboliques.",
    "settings.state_folder": "Données internes de LID",
    "settings.state_help":
      "Modifier ce dossier redémarre LID et déplace de façon sûre les reprises et les index.",
    "settings.connections_title": "Connexions",
    "settings.web_host": "Adresse d’écoute web",
    "settings.web_port": "Port web",
    "settings.direct_port": "Port direct TCP / UDP",
    "settings.upnp": "Activer UPnP pour les transferts directs",
    "settings.proxy_enabled": "Activer le mode proxy SOCKS5",
    "settings.proxy_host": "Hôte du proxy",
    "settings.proxy_port": "Port du proxy",
    "settings.proxy_username": "Identifiant",
    "settings.proxy_password": "Mot de passe",
    "settings.password_keep": "Laisser vide pour conserver le mot de passe enregistré",
    "settings.clear_password": "Supprimer le mot de passe enregistré",
    "settings.proxy_udp": "UDP via le proxy",
    "settings.udp_auto": "Automatique, repli TCP",
    "settings.udp_off": "Désactivé",
    "settings.test_proxy": "Tester le proxy",
    "settings.testing_proxy": "Test du proxy…",
    "settings.proxy_tcp_udp_ok": "Le proxy fonctionne en TCP et l’aller-retour UDP est validé.",
    "settings.proxy_tcp_ok": "Le proxy fonctionne en TCP. UDP est indisponible ; les torrents proxy utiliseront uniquement TCP.",
    "settings.proxy_failed": "Le proxy est inaccessible. Vous pouvez enregistrer, mais les téléchargements proxy resteront bloqués.",
    "settings.advanced": "Avancé",
    "settings.timeout": "Délai du proxy (secondes)",
    "settings.check_interval": "Intervalle de contrôle (secondes)",
    "settings.dns_server": "Serveur DNS distant",
    "settings.dht_nodes": "Nœuds DHT d’amorçage (un hôte:port par ligne)",
    "settings.performance_title": "Performances et récapitulatif",
    "settings.performance_help": "Les limites sont en octets par seconde. Utilisez 0 pour un débit illimité.",
    "settings.upload_limit": "Limite d’envoi (o/s)",
    "settings.download_limit": "Limite de réception (o/s)",
    "settings.connections": "Limite de connexions",
    "settings.file_pool": "Fichiers ouverts",
    "settings.save_interval": "Sauvegarde des reprises (secondes)",
    "settings.previous": "Précédent",
    "settings.next": "Suivant",
    "settings.save": "Enregistrer les réglages",
    "settings.saving": "Enregistrement…",
    "settings.disabled": "désactivé",
    "settings.no_completed": "aucun déplacement automatique",
    "settings.review": "Web : {host}:{port} · Téléchargements : {downloads} · Terminés : {completed} · Proxy : {proxy}",
    "settings.restarting": "LID redémarre…",
    "settings.restarting_help": "Cette page va se reconnecter automatiquement.",
    "drop.direct_title": "Télécharger en direct",
    "drop.direct_text": "Utilise votre connexion Internet.",
    "drop.left": "Déposer à gauche",
    "drop.proxy_title": "Télécharger via proxy",
    "drop.proxy_text": "Transfert exclusivement via le proxy.",
    "drop.right": "Déposer à droite",
    "drop.hint": ".torrent · Relâchez le fichier dans la zone souhaitée",
    "add.eyebrow": "NOUVEAU TRANSFERT",
    "add.title": "Choisissez une route.",
    "add.close": "Fermer",
    "add.mode_aria": "Mode de transfert",
    "add.direct_note": "Votre connexion Internet",
    "add.mode_help":
      "Le mode sera conservé pendant le téléchargement et le seeding.",
    "add.files": "Choisir des fichiers .torrent",
    "add.or_magnet": "OU UN LIEN MAGNET",
    "add.magnet_label": "Lien magnet",
    "add.magnet": "Ajouter le lien",
    "folders.eyebrow": "STOCKAGE",
    "folders.title": "Vos dossiers.",
    "folders.incoming": "Téléchargements en cours",
    "folders.completed": "Téléchargements terminés",
    "folders.completed_placeholder":
      "Choisir un dossier, sur ce disque ou un autre",
    "folders.browse": "Parcourir",
    "folders.browse_incoming": " le dossier des téléchargements en cours",
    "folders.browse_completed": " le dossier des téléchargements terminés",
    "folders.move": "Déplacer les téléchargements terminés",
    "folders.help_move":
      "Les fichiers déjà terminés restent en place. Les transferts en cours gardent leur dossier actuel, puis seront déplacés à leur achèvement. Le seeding continue depuis la destination.",
    "folders.help_machine":
      "Ces dossiers sont sur la machine qui exécute l’application. Choisissez des dossiers existants ; les fichiers seront rangés par mode et par torrent.",
    "folders.save": "Enregistrer les dossiers",
    "folders.saving": "Enregistrement…",
    "folders.browser_aria": "Explorateur de dossiers",
    "folders.path_label": "Chemin à parcourir",
    "folders.go": "Aller",
    "folders.parent": "↑ Dossier parent",
    "folders.loading": "Lecture des dossiers…",
    "folders.subfolders": "Sous-dossiers",
    "folders.empty": "Aucun sous-dossier accessible.",
    "folders.more": "Afficher la suite",
    "folders.back": "Retour",
    "folders.choose": "Choisir ce dossier",
    "folders.shortcut.home": "Dossier personnel",
    "folders.shortcut.root": "Racine",
    "folders.shortcut.drives": "Disques",
    "folders.shortcut.media": "Médias",
    "folders.shortcut.mounts": "Montages",
    "folders.shortcut.user_drives": "Disques utilisateur",
    "proxy.eyebrow": "CONNEXION",
    "proxy.title": "Votre proxy.",
    "proxy.checking": "Vérification…",
    "proxy.tcp": "Trafic TCP",
    "proxy.udp": "Relais UDP",
    "proxy.last_check": "Dernière vérification",
    "proxy.audit": "Audit anti-fuite",
    "proxy.not_certified": "Non certifié",
    "proxy.note":
      "Le test de connexion vérifie l’accès au proxy. L’audit du trafic réseau est un contrôle séparé ; aucune garantie absolue n’est déduite de ce test.",
    "proxy.recheck": "Vérifier la connexion ↗",
    "proxy.functional": "Fonctionnel",
    "proxy.unavailable": "Indisponible",
    "proxy.udp_valid": "Aller-retour validé",
    "proxy.udp_invalid": "Désactivé / non validé",
    "proxy.pending": "En attente",
    "proxy.none": "Aucun proxy configuré",
    "proxy.not_configured": "Non configuré",
    "proxy.short_tcp_udp": "Proxy · TCP + UDP",
    "proxy.short_tcp": "Proxy · TCP",
    "proxy.short_unavailable": "Proxy indisponible",
    "proxy.short_checking": "Vérification du proxy",
    "proxy.message.proxy_checking": "Vérification du proxy…",
    "proxy.message.proxy_active_tcp_udp": "Proxy actif — TCP + UDP",
    "proxy.message.proxy_active_tcp": "Proxy actif — UDP indisponible",
    "proxy.message.proxy_active_udp_no_dht":
      "Proxy actif — UDP disponible, amorçage DHT indisponible",
    "proxy.message.proxy_unavailable":
      "Proxy indisponible : téléchargements proxy bloqués.",
    "proxy.message.proxy_not_configured":
      "Aucun proxy configuré : téléchargement bloqué. Configurez le proxy dans config.yaml.",
    "state.waiting": "En attente",
    "state.checking": "Vérification",
    "state.metadata": "Métadonnées",
    "state.downloading": "Téléchargement",
    "state.finished": "Terminé",
    "state.seeding": "Seeding",
    "state.allocating": "Allocation",
    "state.error": "Erreur",
    "state.paused": "En pause",
    "state.proxy_blocked": "Proxy bloqué",
    "state.moving": "Déplacement en cours",
    "state.move_verifying": "Vérification après déplacement",
    "state.move_pending": "Déplacement en attente",
    "state.storage_unavailable": "Stockage indisponible",
    "state.engine_stopped": "Moteur arrêté",
    "torrent.peer_one": "pair",
    "torrent.peer_many": "pairs",
    "torrent.ratio": "Ratio {value}",
    "torrent.volumes": "Reçu {downloaded} · Envoyé {uploaded}",
    "torrent.last_upload": "Dernier envoi : {value}",
    "torrent.destination": "Destination : {path}",
    "torrent.progress": "Progression de {name}",
    "torrent.resume": "Reprendre",
    "torrent.pause": "Mettre en pause",
    "torrent.remove": "Retirer le torrent et conserver les fichiers",
    "torrent.retry_move": "Réessayer le déplacement",
    "torrent.unit_one": "torrent",
    "torrent.unit_many": "torrents",
    "toast.close": "Fermer le message",
    "toast.retry_move": "Nouvelle tentative demandée.",
    "toast.removed": "Torrent retiré. Les fichiers ont été conservés.",
    "toast.busy": "Un ajout est déjà en cours.",
    "toast.added": "{name} ajouté en mode {mode}.",
    "toast.magnet_added": "Lien magnet ajouté.",
    "toast.proxy_check": "Vérification du proxy en cours…",
    "toast.folders_saved":
      "Dossiers enregistrés et appliqués aux deux moteurs.",
    "toast.settings_saved":
      "Réglages enregistrés et appliqués aux deux moteurs.",
    "connection.interrupted":
      "Connexion au serveur interrompue. Les transferts sont gérés par les moteurs en arrière-plan.",
    "error.unexpected_response": "Réponse inattendue du serveur.",
    "error.invalid_request":
      "Demande invalide. Vérifiez les champs et le mode choisi.",
    "error.pending_storage":
      "Réglages enregistrés mais pas encore appliqués aux deux moteurs. Réenregistrez-les ou redémarrez.",
    "error.session_expired": "Session expirée : rechargez la page.",
    "error.proxy_not_configured":
      "Aucun proxy configuré : téléchargement bloqué. Configurez le proxy dans config.yaml.",
    "error.proxy_unavailable":
      "Proxy indisponible : téléchargements proxy bloqués.",
    "error.too_many_files": "Maximum 20 fichiers par dépôt.",
    "error.invalid_file_type": "Seuls les fichiers .torrent sont acceptés.",
    "error.file_too_large": "Fichier trop volumineux (maximum 10 Mio).",
    "error.torrent_not_found": "Torrent introuvable.",
    "error.duplicate_torrent": "Ce torrent est déjà présent.",
    "error.invalid_torrent": "Torrent ou magnet invalide.",
    "error.engine_unavailable":
      "Moteur torrent indisponible. Redémarrez l’application.",
    "error.storage_collision":
      "Destination déjà occupée : aucun fichier ne sera écrasé. Libérez le dossier puis réessayez.",
    "error.storage_full":
      "Espace insuffisant sur le disque de destination. Les fichiers restent dans le dossier actuel.",
    "error.storage_ambiguous":
      "Le déplacement interrompu a réparti les fichiers. Rassemblez une copie complète dans un seul emplacement puis réessayez.",
    "error.storage_corrupt":
      "Pièces manquantes ou corrompues après déplacement : reprise bloquée, aucun téléchargement automatique.",
    "error.move_in_progress": "Déplacement en cours. Attendez sa fin.",
    "error.move_not_retryable":
      "Aucun déplacement à réessayer pour ce torrent.",
    "error.move_failed":
      "Déplacement échoué : vérifier le disque et les fichiers avant de réessayer.",
    "error.storage_restore_path":
      "Chemin de reprise incohérent : restauration bloquée.",
    "error.storage_unavailable":
      "Stockage indisponible. Vérifiez les dossiers, le disque et les droits.",
    "error.invalid_path": "Le chemin choisi est invalide ou indisponible.",
    "error.invalid_settings": "Certains réglages sont invalides. Vérifiez les valeurs signalées.",
    "error.operation_failed": "L’opération a échoué.",
  },
};

let currentLanguage = "en";
const listeners = new Set();

export function t(key, values = {}) {
  const template = messages[currentLanguage][key] ?? messages.en[key] ?? key;
  return template.replace(/\{(\w+)\}/g, (_, name) => values[name] ?? "");
}

export function getLanguage() {
  return currentLanguage;
}

export function localizedError(code, fallback = "") {
  const key = `error.${code || "operation_failed"}`;
  return messages[currentLanguage][key]
    ? t(key)
    : fallback || t("error.operation_failed");
}

export function applyTranslations(root = document) {
  document.documentElement.lang = currentLanguage;
  document.title = t("app.title");
  root.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = t(node.dataset.i18n);
  });
  for (const [attribute, property] of [
    ["i18nAria", "aria-label"],
    ["i18nTitle", "title"],
    ["i18nPlaceholder", "placeholder"],
  ]) {
    root
      .querySelectorAll(
        `[data-${attribute.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}]`,
      )
      .forEach((node) => {
        node.setAttribute(property, t(node.dataset[attribute]));
      });
  }
  const toggle = document.getElementById("language-toggle");
  if (toggle) {
    toggle.dataset.language = currentLanguage;
    toggle.setAttribute("aria-label", t("language.toggle"));
    toggle.setAttribute("title", t("language.toggle"));
    toggle.querySelectorAll("span").forEach((node) => {
      node.classList.toggle(
        "active",
        node.dataset.language === currentLanguage,
      );
    });
  }
}

export function setLanguage(language, persist = true) {
  currentLanguage = language === "fr" ? "fr" : "en";
  if (persist) {
    try {
      localStorage.setItem(STORAGE_KEY, currentLanguage);
    } catch {}
  }
  applyTranslations();
  listeners.forEach((listener) => listener(currentLanguage));
}

export function onLanguageChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function initI18n() {
  try {
    currentLanguage = localStorage.getItem(STORAGE_KEY) === "fr" ? "fr" : "en";
  } catch {
    currentLanguage = "en";
  }
  applyTranslations();
  const toggle = document.getElementById("language-toggle");
  if (toggle)
    toggle.onclick = () => setLanguage(currentLanguage === "en" ? "fr" : "en");
}
