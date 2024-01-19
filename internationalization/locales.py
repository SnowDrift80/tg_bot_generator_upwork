# simple string localization class
# all application string literals must be maintained here 
# in the StringLiteral.translations dictionary
#
# the class method will be called ad hoc wherever needed
# in the code to return translation according to 
# telegram preferred user locale.

class StringLiteral:
    translations = {
        'en': {
            'Academic Lecture': 'Academic Lecture',
            'Poetry': 'Poetry',
            '<b>Max allowed tasks is.</b>\nCurrently task(s) active.\n\nRequest rejected.': '<b>Max allowed tasks is.</b>\nCurrently task(s) active.\n\nRequest rejected.',
            '<b>Please review main chapters and choose option on how to proceed.</b>': '<b>Please review main chapters and choose option on how to proceed.</b>',
            'Please enter your instructions:': 'Please enter your instructions:',
            'scaffolding document structure...': 'scaffolding document structure...',
            '<b><u>Suggested document structure:</u></b>': '<b><u>Suggested document structure:</u></b>',
            'processing parent-chapter': 'processing parent-chapter',
            'processing sub-chapter': 'processing sub-chapter',
            'What type of document would you like to create?': 'What type of document would you like to create?',
            'Here\'s your Word document!': 'Here\'s your Word document!',
            'cancel': 'cancel',
            'approve': 'approve',
            'have a document of your choice created': 'have a document of your choice created',
            'Enter \'/create\' in the Telegram command line and post it to activate the document generator.': 'Enter \'/create\' in the Telegram command line and submit it to activate the document generator.',
            'lists available bot commands': 'lists available bot commands',
            'Enter \'/help\' in the Telegram command line and post it to display the help information.': 'Enter \'/help\' in the Telegram command line and post it to display the help information.',
        },
        'de': {
            'Academic Lecture': 'Akademischer Vortrag',
            'Poetry': 'Poesie',
            '<b>Max allowed tasks is.</b>\nCurrently task(s) active.\n\nRequest rejected.': '<b>Maximal zulässige Anzahl von Aufgaben ist.</b>\nZurzeit sind Aufgabe(n) aktiv. Anforderung abgelehnt.',
            '<b>Please review main chapters and choose option on how to proceed.</b>': '<b>Bitte überprüfen Sie die Hauptkapitel und wählen Sie eine Option für das weitere Vorgehen.</b>',
            'Please enter your instructions:': 'Bitte geben Sie Ihre Anweisungen ein:',
            'scaffolding document structure...': 'Generierung der Dokumentenstruktur...',
            '<b><u>Suggested document structure:</u></b>': '<b><u>Vorgeschlagene Dokumentenstruktur:</u></b>',
            'processing parent-chapter': 'Verarbeitung des Hauptkapitels ',
            'processing sub-chapter': 'Verarbeitung der Unterkapitel ','m'
            'What type of document would you like to create?': 'Welche Art von Dokument möchten Sie erstellen?',
            'Here\'s your Word document!': 'Ihr Word Dokument ist bereit zum Download!',
            'cancel': 'abbrechen',
            'approve': 'genehmigen',
            'have a document of your choice created': 'ein Dokument Ihrer Wahl erstellen lassen',
            'Enter \'/create\' in the Telegram command line and post it to activate the document generator.': 'Geben Sie \'/create\' in die Telegramm-Befehlszeile ein und senden Sie es, um den Dokumentengenerator zu aktivieren.',
            'lists available bot commands': 'listet die verfügbaren Bot-Befehle auf',
            'Enter \'/help\' in the Telegram command line and post it to display the help information.': 'Geben Sie \'/help\' in die Telegramm-Befehlszeile ein und senden Sie es, um die Hilfeinformationen anzuzeigen.',
        },
        'fr': {
            'Academic Lecture': 'Conférence académique',
            'Poetry': 'Poésie',
            '<b>Max allowed tasks is.</b>\nCurrently task(s) active.\n\nRequest rejected.': '<b>Le maximum de tâches autorisées est de.</b>\n Actuellement tâche(s) active(s).\n\n</b> Demande rejetée.',
            '<b>Please review main chapters and choose option on how to proceed.</b>': '<b>Veuillez examiner les principaux chapitres et choisir une option sur la façon de procéder.</b>',
            'Please enter your instructions:': 'Veuillez donner vos instructions :',
            'scaffolding document structure...': 'conceptionner la structure du document...',
            '<b><u>Suggested document structure:</u></b>': '<b><u>Structure suggérée du document:</u></b>',
            'processing parent-chapter': 'traitement du chapitre-parent ',
            'processing sub-chapter': 'traitement du sous-chapitre ',
            'What type of document would you like to create?': 'Quel type de document voulez-vous créer ?',
            'Here\'s your Word document!': 'Voilà votre document Word!',
            'cancel': 'annuler',
            'approve': 'approuver',
            'have a document of your choice created': 'faire créer un document de votre choix',
            'Enter \'/create\' in the Telegram command line and post it to activate the document generator.': 'Saisissez \'/créer\' dans la ligne de commande Telegram et envoyez-la pour activer le générateur de documents.',
            'lists available bot commands': 'liste les commandes de robot disponibles',
            'Enter \'/help\' in the Telegram command line and post it to display the help information.': 'Entrez \'/help\' dans la ligne de commande Telegram et soumettez-la pour afficher les informations d\'aide.',
        },
    }
    
    
    # use key to get the (translated) value
    @classmethod
    def get_translation(cls, user_language, translation_key):
        try:
            return cls.translations[user_language][translation_key]
        except KeyError as e:
            # return translation key (source expression) if key not found
            print("Translation_key {translation_key} not found.")
            return translation_key
        

    # reverse the translation and get the key
    @classmethod
    def reverse_lookup(cls, target_value):
        for language_code, translations in cls.translations.items():
            for key, value in translations.items():
                if value == target_value:
                    return key
    # no error handling (key not found) needed, because impossible, as
    # the target_value itself comes from the translation.