## SEED-AUTORM-001 — Un torrent terminé inactif depuis plus de 7 jours est retiré, fichiers conservés

Implement: `Engine.tick` / `Engine._sweep_inactive` dans `app/engine.py` via le retrait existant `Engine.action(key, "remove")` (même sémantique : index + `.source`/`.resume` retirés, fichiers payload conservés), et la réconciliation de `Manager.known` dans `Manager.collect` dans `app/manager.py`.
Out of scope: suppression des fichiers téléchargés ; notification toast lors d'un retrait automatique ; nouveau réglage de seuil (constante `INACTIVE_TTL = 7*24*3600`, comparaison stricte `>`).

Test: unit · `tests/test_seeding.py` · `test_seed_autorm_001_sweep_removes_only_stale_finished_seeds`
- Given: un moteur avec des records `seeding` (dernier envoi il y a 8 jours ; envoi il y a 1 heure ; jamais envoyé mais `finished_at` il y a 8 jours ; jamais envoyé et `finished_at` il y a 1 heure), un record `downloading` vieux de 30 jours, un record `seeding` en pause vieux de 30 jours, et un record `seeding` vieux de 8 jours en `proxy_blocked`
- When: `Engine._sweep_inactive(now)` est appelé
- Then: seuls le seeding inactif depuis 8 jours et le seeding jamais envoyé terminé il y a 8 jours sont retirés (fichiers payload conservés, `.source`/`.resume` supprimés), tous les autres sont conservés, et un seeding vieux d'exactement 604800 s est conservé (seuil strict `>`)

Test: unit · `tests/test_seeding.py` · `test_seed_autorm_001_manager_prunes_known_after_engine_removal`
- Given: un manager dont `known` contient un id absent du snapshot du même mode
- When: la réconciliation du snapshot est appliquée
- Then: l'entrée périmée est retirée de `known` sans toucher les ids de l'autre mode
