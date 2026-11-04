"""Language policy for the seven verified editions."""
NATIVE_ENGLISH={'London Racer','Holiday Racer','Europe Racer'}


def native_english(game):
    return game in NATIVE_ENGLISH
