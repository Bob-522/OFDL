from datetime import datetime
from typing import Optional

class Events:
    def __init__(self):
        pass

    def display_event(self, *textes: str, niveau_titre: Optional[int] = None):
        time = datetime.now().strftime("%H:%M:%S")
        titre = ''
        spacer = ' '
        if niveau_titre == 1:
            titre = '============================================================'
        elif niveau_titre == 2:
            titre = '------------------------------------------------------------'

        if niveau_titre != None:
            print(time + spacer + titre)

        for line in textes:
            print(time + spacer + line)
            
        if niveau_titre != None:
            print(time + spacer + titre)

