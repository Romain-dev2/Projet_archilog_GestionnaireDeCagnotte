"""Flask configuration for Archilog."""

# Chargé via app.config.from_object(Config) dans views.py au démarrage de l'app.
import os
import secrets


class Config:
    """Flask application settings.

    SECRET_KEY:
        Lu depuis la variable d'environnement ARCHILOG_SECRET_KEY.
        Si absente (développement), une clé aléatoire est générée à chaque
        démarrage — les messages flash et les sessions ne survivent alors pas
        à un redémarrage du serveur. Toujours définir cette variable en
        production et en déploiement persistant.
    """

    # secrets.token_hex(32) génère 256 bits d'entropie — suffisant pour
    # la signature des cookies Flask (HMAC-SHA1). Ne jamais logger cette valeur.
    SECRET_KEY: str = os.environ.get("ARCHILOG_SECRET_KEY") or secrets.token_hex(32)