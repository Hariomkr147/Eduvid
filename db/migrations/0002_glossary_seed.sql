-- Pilot glossary: one row per term. Spoken forms are written the way they are said.
-- Terms only (facts), no textbook text.
INSERT INTO glossary (subject, term_en, hindi_term, hinglish_say, hindi_say, english_say, caption, notes) VALUES
-- maths: surface areas and volumes
('maths', 'cylinder',             'बेलन',                'सिलेंडर',                'बेलन',                    'cylinder',             'cylinder',             ''),
('maths', 'cone',                 'शंकु',                'कोन',                    'शंकु',                    'cone',                 'cone',                 ''),
('maths', 'sphere',               'गोला',                'स्फीयर',                 'गोला',                    'sphere',               'sphere',               ''),
('maths', 'hemisphere',           'अर्धगोला',            'हेमिस्फीयर',             'अर्धगोला',                'hemisphere',           'hemisphere',           ''),
('maths', 'cuboid',               'घनाभ',                'क्यूबॉइड',               'घनाभ',                    'cuboid',               'cuboid',               ''),
('maths', 'cube',                 'घन',                  'क्यूब',                  'घन',                      'cube',                 'cube',                 ''),
('maths', 'radius',               'त्रिज्या',            'रेडियस',                 'त्रिज्या',                'radius',               'radius',               'symbol r is said आर'),
('maths', 'diameter',             'व्यास',               'डायमीटर',                'व्यास',                   'diameter',             'diameter',             ''),
('maths', 'height',               'ऊँचाई',               'हाइट',                   'ऊँचाई',                   'height',               'height',               'symbol h is said एच'),
('maths', 'slant height',         'तिर्यक ऊँचाई',        'स्लांट हाइट',            'तिर्यक ऊँचाई',            'slant height',         'slant height',         'symbol l is said एल'),
('maths', 'circumference',        'परिधि',               'सरकमफ़रेंस',             'परिधि',                   'circumference',        'circumference',        ''),
('maths', 'surface area',         'पृष्ठीय क्षेत्रफल',   'सरफेस एरिया',            'पृष्ठीय क्षेत्रफल',       'surface area',         'surface area',         ''),
('maths', 'curved surface area',  'वक्र पृष्ठीय क्षेत्रफल', 'कर्व्ड सरफेस एरिया', 'वक्र पृष्ठीय क्षेत्रफल',  'curved surface area',  'curved surface area',  'caption may use CSA'),
('maths', 'total surface area',   'कुल पृष्ठीय क्षेत्रफल', 'टोटल सरफेस एरिया',    'कुल पृष्ठीय क्षेत्रफल',   'total surface area',   'total surface area',   'caption may use TSA'),
('maths', 'volume',               'आयतन',                'वॉल्यूम',                'आयतन',                    'volume',               'volume',               ''),
('maths', 'pi',                   'पाई',                 'पाई',                    'पाई',                     'pi',                   'π',                    'never write the symbol in say text'),
('maths', 'squared',              'वर्ग',                'स्क्वेयर्ड',             'का वर्ग',                 'squared',              '²',                    'r squared: आर स्क्वेयर्ड'),
-- science: motion
('science', 'distance',           'दूरी',                'डिस्टेंस',               'दूरी',                    'distance',             'distance',             ''),
('science', 'displacement',       'विस्थापन',            'डिस्प्लेसमेंट',          'विस्थापन',                'displacement',         'displacement',         ''),
('science', 'speed',              'चाल',                 'स्पीड',                  'चाल',                     'speed',                'speed',                ''),
('science', 'velocity',           'वेग',                 'वेलोसिटी',               'वेग',                     'velocity',             'velocity',             ''),
('science', 'acceleration',       'त्वरण',               'एक्सेलरेशन',             'त्वरण',                   'acceleration',         'acceleration',         ''),
-- science: atoms and molecules
('science', 'atom',               'परमाणु',              'एटम',                    'परमाणु',                  'atom',                 'atom',                 ''),
('science', 'molecule',           'अणु',                 'मॉलिक्यूल',              'अणु',                     'molecule',             'molecule',             ''),
('science', 'mole',               'मोल',                 'मोल',                    'मोल',                     'mole',                 'mole',                 ''),
('science', 'valency',            'संयोजकता',            'वैलेंसी',                'संयोजकता',                'valency',              'valency',              ''),
('science', 'atomic mass',        'परमाणु द्रव्यमान',    'एटॉमिक मास',             'परमाणु द्रव्यमान',        'atomic mass',          'atomic mass',          ''),
('science', 'ion',                'आयन',                 'आयन',                    'आयन',                     'ion',                  'ion',                  ''),
-- science: the cell
('science', 'cell',               'कोशिका',              'सेल',                    'कोशिका',                  'cell',                 'cell',                 ''),
('science', 'nucleus',            'केंद्रक',             'न्यूक्लियस',             'केंद्रक',                 'nucleus',              'nucleus',              ''),
('science', 'cell membrane',      'कोशिका झिल्ली',       'सेल मेम्ब्रेन',          'कोशिका झिल्ली',           'cell membrane',        'cell membrane',        ''),
('science', 'cell wall',          'कोशिका भित्ति',       'सेल वॉल',                'कोशिका भित्ति',           'cell wall',            'cell wall',            ''),
('science', 'cytoplasm',          'कोशिकाद्रव्य',        'साइटोप्लाज़्म',          'कोशिकाद्रव्य',            'cytoplasm',            'cytoplasm',            ''),
('science', 'mitochondria',       'सूत्रकणिका',          'माइटोकॉन्ड्रिया',        'सूत्रकणिका',              'mitochondria',         'mitochondria',         ''),
('science', 'chloroplast',        'हरितलवक',             'क्लोरोप्लास्ट',          'हरितलवक',                 'chloroplast',          'chloroplast',          '')
ON CONFLICT (subject, term_en) DO NOTHING;
