# Volontairement vide — déclare tests/ comme package Python.
#
# Sans ce fichier, pytest peut quand même découvrir les tests (mode rootdir),
# mais les imports relatifs entre fichiers de test ne fonctionneraient pas.
# Le garder vide est la convention recommandée pour les suites de tests.