#!/usr/bin/env python3
"""Write index.<lang>.qmd from index.qmd by exact text replacement.

The homepage carries a lot of markup (hero, motion scripts, listings). Translating it by
replacement keeps that markup identical to the English page: every English string below must
occur in index.qmd exactly as often as stated, or the script stops, so an edit to the English
homepage that a translation does not cover is caught instead of silently left in English.

Usage: python3 scripts/translate_index.py   (writes index.es.qmd and index.de.qmd)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (English, Spanish, German[, expected count]) in page order.
STRINGS = [
    ('pagetitle: "Dr. Adriana L. Ruiz-Rizzo"', 'pagetitle: "Dra. Adriana L. Ruiz-Rizzo"', 'pagetitle: "Dr. Adriana L. Ruiz-Rizzo"'),
    ('description: "Cognitive and clinical neuroscientist studying how aging and early cognitive decline reshape attention, memory, and brain networks, using multimodal MRI."',
     'description: "Neurocientífica cognitiva y clínica que estudia cómo el envejecimiento transforma la atención, la memoria y las redes cerebrales, con resonancia magnética."',
     'description: "Kognitive und klinische Neurowissenschaftlerin. Sie untersucht mit MRT, wie Altern und früher Abbau Aufmerksamkeit, Gedächtnis und Hirnnetzwerke verändern."'),
    ("image: assets/social/index.png", "image: assets/social/es/index.png", "image: assets/social/de/index.png"),
    ('image-alt: "Title card: Dr. Adriana L. Ruiz-Rizzo, cognitive and clinical neuroscientist, with her portrait, on a dark background with a network pattern."',
     'image-alt: "Tarjeta: Dra. Adriana L. Ruiz-Rizzo, neurocientífica cognitiva y clínica, con su retrato, sobre un fondo oscuro con un patrón de red."',
     'image-alt: "Titelkarte: Dr. Adriana L. Ruiz-Rizzo, kognitive und klinische Neurowissenschaftlerin, mit ihrem Porträt, auf dunklem Hintergrund mit Netzwerkmuster."'),
    ('share-card-title: "Dr. Adriana L. Ruiz-Rizzo"', 'share-card-title: "Dra. Adriana L. Ruiz-Rizzo"', 'share-card-title: "Dr. Adriana L. Ruiz-Rizzo"'),
    ('share-card-tagline: "Aging, early cognitive decline, visual attention, and the organization of brain networks"',
     'share-card-tagline: "Envejecimiento, deterioro cognitivo temprano, atención visual y organización de las redes cerebrales"',
     'share-card-tagline: "Altern, früher kognitiver Abbau, visuelle Aufmerksamkeit und die Organisation von Hirnnetzwerken"'),
    ('  title: "Dr. Adriana L. Ruiz-Rizzo · Cognitive and clinical neuroscientist"',
     '  title: "Dra. Adriana L. Ruiz-Rizzo · Neurocientífica cognitiva y clínica"',
     '  title: "Dr. Adriana L. Ruiz-Rizzo · Kognitive und klinische Neurowissenschaft"', 2),
    ('"jobTitle": "Associate researcher"', '"jobTitle": "Investigadora asociada"', '"jobTitle": "Wissenschaftliche Mitarbeiterin"'),
    ('"description": "Cognitive and clinical neuroscientist"', '"description": "Neurocientífica cognitiva y clínica"', '"description": "Kognitive und klinische Neurowissenschaftlerin"'),
    ('"name": "Jena University Hospital", "department": {"@type": "Organization", "name": "Department of Neurology"}',
     '"name": "Hospital Universitario de Jena", "department": {"@type": "Organization", "name": "Departamento de Neurología"}',
     '"name": "Universitätsklinikum Jena", "department": {"@type": "Organization", "name": "Klinik für Neurologie"}'),
    ('"knowsAbout": ["Cognitive aging", "Visual attention", "Subjective cognitive decline", "Mild cognitive impairment", "Functional connectivity", "Diffusion MRI"]',
     '"knowsAbout": ["Envejecimiento cognitivo", "Atención visual", "Deterioro cognitivo subjetivo", "Deterioro cognitivo leve", "Conectividad funcional", "Resonancia magnética de difusión"]',
     '"knowsAbout": ["Kognitives Altern", "Visuelle Aufmerksamkeit", "Subjektiver kognitiver Abbau", "Leichte kognitive Beeinträchtigung", "Funktionelle Konnektivität", "Diffusions-MRT"]'),
    ('"url": "https://alruizzo.github.io/",', '"url": "https://alruizzo.github.io/es/",', '"url": "https://alruizzo.github.io/de/",'),
    ('aria-label="Pause background animation"', 'aria-label="Pausar la animación de fondo"', 'aria-label="Hintergrundanimation anhalten"'),
    ('<span class="rr-wipe">Dr. Adriana L. Ruiz-Rizzo</span>', '<span class="rr-wipe">Dra. Adriana L. Ruiz-Rizzo</span>', '<span class="rr-wipe">Dr. Adriana L. Ruiz-Rizzo</span>'),
    ("[Studying how aging and the earliest stages of cognitive decline reshape attention, memory, and the organization of brain networks.]{.rr-statement}",
     "[Estudia cómo el envejecimiento y las primeras fases del deterioro cognitivo transforman la atención, la memoria y la organización de las redes cerebrales.]{.rr-statement}",
     "[Sie untersucht, wie Altern und die frühesten Stadien kognitiven Abbaus Aufmerksamkeit, Gedächtnis und die Organisation von Hirnnetzwerken verändern.]{.rr-statement}"),
    ("[Her research combines multimodal MRI with computational models of visual attention to identify early markers of decline and to inform prevention and early intervention.]{.rr-support}",
     "[Su investigación combina la resonancia magnética multimodal con modelos computacionales de la atención visual para identificar marcadores tempranos del deterioro y orientar la prevención y la intervención temprana.]{.rr-support}",
     "[Ihre Forschung verbindet multimodale MRT mit computationalen Modellen visueller Aufmerksamkeit, um frühe Marker des Abbaus zu identifizieren und Prävention und frühe Intervention zu unterstützen.]{.rr-support}"),
    ("[Explore the research](research.qmd)", "[Explorar la investigación](research.qmd)", "[Zur Forschung](research.qmd)"),
    ("[Publications](publications.qmd){.rr-btn .rr-btn-secondary}", "[Publicaciones](publications.qmd){.rr-btn .rr-btn-secondary}", "[Publikationen](publications.qmd){.rr-btn .rr-btn-secondary}"),
    ("[Get in touch](contact.qmd)", "[Contactar](contact.qmd)", "[Kontakt aufnehmen](contact.qmd)", 2),
    ('alt="Portrait of Adriana L. Ruiz-Rizzo"', 'alt="Retrato de Adriana L. Ruiz-Rizzo"', 'alt="Porträt von Adriana L. Ruiz-Rizzo"'),
    ('// The slow background drift lasts longer than 5 s, so the pause control is revealed with it',
     '// The slow background drift lasts longer than 5 s, so the pause control is revealed with it',
     '// The slow background drift lasts longer than 5 s, so the pause control is revealed with it'),
    ('btn.setAttribute("aria-label", paused ? "Play background animation" : "Pause background animation");',
     'btn.setAttribute("aria-label", paused ? "Reanudar la animación de fondo" : "Pausar la animación de fondo");',
     'btn.setAttribute("aria-label", paused ? "Hintergrundanimation fortsetzen" : "Hintergrundanimation anhalten");'),
    ("## Education {.unlisted}", "## Formación {.unlisted}", "## Ausbildung {.unlisted}"),
    ("## Research positions {.unlisted}", "## Puestos de investigación {.unlisted}", "## Forschungspositionen {.unlisted}"),
    ("## Recognition and funding {.unlisted}", "## Premios y financiación {.unlisted}", "## Auszeichnungen und Förderung {.unlisted}"),
    ('<span class="rr-eyebrow">Peer-reviewed work published in</span>', '<span class="rr-eyebrow">Investigación revisada por pares publicada en revistas científicas</span>', '<span class="rr-eyebrow">Begutachtete Arbeiten erschienen in</span>'),
    ('aria-label="Pause the moving journal list"', 'aria-label="Pausar la lista de revistas en movimiento"', 'aria-label="Bewegte Zeitschriftenliste anhalten"'),
    ('btn.setAttribute("aria-label", paused ? "Play the moving journal list" : "Pause the moving journal list");',
     'btn.setAttribute("aria-label", paused ? "Reanudar la lista de revistas en movimiento" : "Pausar la lista de revistas en movimiento");',
     'btn.setAttribute("aria-label", paused ? "Bewegte Zeitschriftenliste fortsetzen" : "Bewegte Zeitschriftenliste anhalten");'),
    ("[Why it matters]{.rr-eyebrow}", "[Por qué importa]{.rr-eyebrow}", "[Warum es wichtig ist]{.rr-eyebrow}"),
    ("## Decline may begin before diagnosis {.rr-section-title}", "## El deterioro puede empezar antes del diagnóstico {.rr-section-title}", "## Der Abbau kann vor der Diagnose beginnen {.rr-section-title}"),
    ("Changes in attention, memory, and brain connectivity can start years before dementia is diagnosed. Adriana showed that patients with amnestic mild cognitive impairment due to Alzheimer's disease, an at-risk stage of dementia, made more errors than matched controls when identifying overlapping shapes, and that these errors went with slower visual processing. In older adults who notice their own decline before standard tests can detect it, her work links those complaints to a similar slowing and, in people with lower neurite density in frontal white matter, to lower connectivity in an attention-related brain network.",
     "Los cambios en la atención, la memoria y la conectividad cerebral pueden empezar años antes de que se diagnostique una demencia. Adriana mostró que los pacientes con deterioro cognitivo leve amnésico debido a la enfermedad de Alzheimer, una fase de riesgo de demencia, cometían más errores que controles emparejados al identificar formas superpuestas, y que esos errores iban unidos a un procesamiento visual más lento. En personas mayores que notan su propio deterioro antes de que las pruebas habituales puedan detectarlo, su trabajo relaciona esas quejas con un enlentecimiento similar y, en personas con menor densidad de neuritas en la sustancia blanca frontal, con una menor conectividad en una red cerebral relacionada con la atención.",
     "Veränderungen von Aufmerksamkeit, Gedächtnis und Hirnkonnektivität können Jahre vor der Diagnose einer Demenz beginnen. Adriana zeigte, dass Patientinnen und Patienten mit amnestischer leichter kognitiver Beeinträchtigung infolge der Alzheimer-Krankheit, einem Risikostadium der Demenz, beim Erkennen überlappender Formen mehr Fehler machten als passende Kontrollpersonen und dass diese Fehler mit einer langsameren visuellen Verarbeitung einhergingen. Bei älteren Menschen, die ihren eigenen Abbau bemerken, bevor Standardtests ihn erfassen können, verbindet ihre Arbeit diese Beschwerden mit einer ähnlichen Verlangsamung und, bei geringerer Neuritendichte in der frontalen weißen Substanz, mit geringerer Konnektivität in einem aufmerksamkeitsbezogenen Hirnnetzwerk."),
    ("Measuring such early changes precisely, and understanding which brain systems carry them, is the basis for detecting decline sooner and for testing interventions, from alertness training to physical activity and diet, that may support cognitive health in aging.",
     "Medir con precisión estos cambios tempranos, y entender qué sistemas cerebrales los sostienen, es la base para detectar antes el deterioro y para poner a prueba intervenciones, del entrenamiento de la alerta a la actividad física y la alimentación, que podrían favorecer la salud cognitiva en el envejecimiento.",
     "Solche frühen Veränderungen genau zu messen und zu verstehen, welche Hirnsysteme sie tragen, ist die Grundlage dafür, Abbau früher zu erkennen und Interventionen zu prüfen, vom Alertness-Training bis zu Bewegung und Ernährung, die die kognitive Gesundheit im Alter unterstützen könnten."),
    ("[Research themes]{.rr-eyebrow}", "[Temas de investigación]{.rr-eyebrow}", "[Forschungsthemen]{.rr-eyebrow}"),
    ("## Four connected questions", "## Cuatro preguntas conectadas", "## Vier verbundene Fragen"),
    ("[All research themes](research.qmd){.rr-more}", "[Todos los temas de investigación](research.qmd){.rr-more}", "[Alle Forschungsthemen](research.qmd){.rr-more}"),
    ("[Visual attention]{.rr-theme-label}", "[Atención visual]{.rr-theme-label}", "[Visuelle Aufmerksamkeit]{.rr-theme-label}"),
    ("### Why does visual processing slow with age?", "### ¿Por qué se vuelve más lento el procesamiento visual con la edad?", "### Warum verlangsamt sich die visuelle Verarbeitung im Alter?"),
    ("Theory-based measures of attention, such as processing speed and short-term memory capacity, related to brain networks across the adult lifespan.",
     "Medidas de la atención basadas en teoría, como la velocidad de procesamiento y la capacidad de la memoria a corto plazo, relacionadas con las redes cerebrales a lo largo de la vida adulta.",
     "Theoriebasierte Maße der Aufmerksamkeit wie Verarbeitungsgeschwindigkeit und Kurzzeitgedächtniskapazität, bezogen auf Hirnnetzwerke über die gesamte Erwachsenenlebensspanne."),
    ('[Read more](research.qmd#visual-attention){.rr-more .rr-card-foot aria-label="Read more about visual attention"}',
     '[Leer más](research.qmd#visual-attention){.rr-more .rr-card-foot aria-label="Leer más sobre atención visual"}',
     '[Mehr erfahren](research.qmd#visual-attention){.rr-more .rr-card-foot aria-label="Mehr über visuelle Aufmerksamkeit"}'),
    ("[Brain networks]{.rr-theme-label}", "[Redes cerebrales]{.rr-theme-label}", "[Hirnnetzwerke]{.rr-theme-label}"),
    ("### How does the brain's organization support cognition?", "### ¿Cómo sustenta la organización del cerebro la cognición?", "### Wie trägt die Organisation des Gehirns die Kognition?"),
    ("Resting-state and diffusion MRI show how functional networks and white-matter pathways relate to individual differences in attention and memory.",
     "La resonancia magnética en reposo y de difusión muestra cómo las redes funcionales y las vías de sustancia blanca se relacionan con las diferencias individuales en la atención y la memoria.",
     "Ruhezustands- und Diffusions-MRT zeigen, wie funktionelle Netzwerke und Bahnen der weißen Substanz mit individuellen Unterschieden in Aufmerksamkeit und Gedächtnis zusammenhängen."),
    ('[Read more](research.qmd#brain-networks){.rr-more .rr-card-foot aria-label="Read more about brain networks"}',
     '[Leer más](research.qmd#brain-networks){.rr-more .rr-card-foot aria-label="Leer más sobre redes cerebrales"}',
     '[Mehr erfahren](research.qmd#brain-networks){.rr-more .rr-card-foot aria-label="Mehr über Hirnnetzwerke"}'),
    ("[Cognitive decline and dementia]{.rr-theme-label}", "[Deterioro cognitivo y demencia]{.rr-theme-label}", "[Kognitiver Abbau und Demenz]{.rr-theme-label}"),
    ("### What are the earliest signs of decline?", "### ¿Cuáles son los primeros signos del deterioro?", "### Was sind die frühesten Anzeichen des Abbaus?"),
    ("From presymptomatic familial Alzheimer's disease to subjective cognitive decline and mild cognitive impairment.",
     "De la enfermedad de Alzheimer familiar presintomática al deterioro cognitivo subjetivo y al deterioro cognitivo leve.",
     "Von der präsymptomatischen familiären Alzheimer-Krankheit bis zum subjektiven kognitiven Abbau und zur leichten kognitiven Beeinträchtigung."),
    ('[Read more](research.qmd#cognitive-decline){.rr-more .rr-card-foot aria-label="Read more about cognitive decline and dementia"}',
     '[Leer más](research.qmd#cognitive-decline){.rr-more .rr-card-foot aria-label="Leer más sobre deterioro cognitivo y demencia"}',
     '[Mehr erfahren](research.qmd#cognitive-decline){.rr-more .rr-card-foot aria-label="Mehr über kognitiven Abbau und Demenz"}'),
    ("[Lifestyle and interventions]{.rr-theme-label}", "[Estilo de vida e intervenciones]{.rr-theme-label}", "[Lebensstil und Interventionen]{.rr-theme-label}"),
    ("### Can attention and brain health be supported?", "### ¿Se pueden favorecer la atención y la salud cerebral?", "### Lassen sich Aufmerksamkeit und Hirngesundheit unterstützen?"),
    ("Alertness training, physical activity, and diet, studied in training studies, a randomized controlled trial, and a longitudinal cohort.",
     "Entrenamiento de la alerta, actividad física y alimentación, estudiados en estudios de entrenamiento, un ensayo controlado aleatorizado y una cohorte longitudinal.",
     "Alertness-Training, Bewegung und Ernährung, untersucht in Trainingsstudien, einer randomisierten kontrollierten Studie und einer Längsschnittkohorte."),
    ('[Read more](research.qmd#lifestyle-interventions){.rr-more .rr-card-foot aria-label="Read more about lifestyle and interventions"}',
     '[Leer más](research.qmd#lifestyle-interventions){.rr-more .rr-card-foot aria-label="Leer más sobre estilo de vida e intervenciones"}',
     '[Mehr erfahren](research.qmd#lifestyle-interventions){.rr-more .rr-card-foot aria-label="Mehr über Lebensstil und Interventionen"}'),
    ("The same approach extends to [multiple sclerosis, Parkinson's disease, and depression](research.qmd#clinical-neuroscience), and to [machine learning on health and social data](research.qmd#data-science).",
     "El mismo enfoque se extiende a la [esclerosis múltiple, la enfermedad de Parkinson y la depresión](research.qmd#clinical-neuroscience), y al [aprendizaje automático con datos de salud y datos sociales](research.qmd#data-science).",
     "Derselbe Ansatz erstreckt sich auf [Multiple Sklerose, Parkinson-Krankheit und Depression](research.qmd#clinical-neuroscience) sowie auf [Machine Learning mit Gesundheits- und Sozialdaten](research.qmd#data-science)."),
    ("[Selected publications]{.rr-eyebrow}", "[Publicaciones seleccionadas]{.rr-eyebrow}", "[Ausgewählte Publikationen]{.rr-eyebrow}"),
    ("## Representative work", "## Trabajos representativos", "## Repräsentative Arbeiten"),
    ("Studies that show the range of the research, from mechanisms of attention in aging to lifestyle and early decline.",
     "Estudios que muestran el alcance de la investigación, de los mecanismos de la atención en el envejecimiento al estilo de vida y el deterioro temprano. Los títulos se citan tal como se publicaron.",
     "Studien, die die Bandbreite der Forschung zeigen, von Aufmerksamkeitsmechanismen im Alter bis zu Lebensstil und frühem Abbau. Titel werden wie veröffentlicht zitiert."),
    ("[All publications](publications.qmd){.rr-more}", "[Todas las publicaciones](publications.qmd){.rr-more}", "[Alle Publikationen](publications.qmd){.rr-more}"),
    ("[News]{.rr-eyebrow}", "[Novedades]{.rr-eyebrow}", "[Neuigkeiten]{.rr-eyebrow}"),
    ("## Recent updates", "## Lo más reciente", "## Aktuelles"),
    ("[All news](news.qmd){.rr-more}", "[Todas las novedades](news.qmd){.rr-more}", "[Alle Neuigkeiten](news.qmd){.rr-more}"),
    ("[Trajectory]{.rr-eyebrow}", "[Trayectoria]{.rr-eyebrow}", "[Werdegang]{.rr-eyebrow}"),
    ('## An international research path {.rr-section-title style="margin-bottom: var(--rr-space-6);"}',
     '## Una trayectoria de investigación internacional {.rr-section-title style="margin-bottom: var(--rr-space-6);"}',
     '## Ein internationaler Forschungsweg {.rr-section-title style="margin-bottom: var(--rr-space-6);"}'),
    ('<div class="rr-when rr-num">2003 to 2011</div><div class="rr-where">Medellín</div><div class="rr-what">Universidad de Antioquia and the Grupo de Neurociencias de Antioquia: familial Alzheimer\'s disease research</div>',
     '<div class="rr-when rr-num">2003 a 2011</div><div class="rr-where">Medellín</div><div class="rr-what">Universidad de Antioquia y Grupo de Neurociencias de Antioquia: investigación sobre la enfermedad de Alzheimer familiar</div>',
     '<div class="rr-when rr-num">2003 bis 2011</div><div class="rr-where">Medellín</div><div class="rr-what">Universidad de Antioquia und Grupo de Neurociencias de Antioquia: Forschung zur familiären Alzheimer-Krankheit</div>'),
    ('<div class="rr-when rr-num">2011 to 2013</div><div class="rr-where">Maastricht</div><div class="rr-what">M.Sc., Maastricht University; research internship at the Donders Institute, Nijmegen</div>',
     '<div class="rr-when rr-num">2011 a 2013</div><div class="rr-where">Maastricht</div><div class="rr-what">Maestría, Maastricht University; pasantía de investigación en el Donders Institute, Nimega</div>',
     '<div class="rr-when rr-num">2011 bis 2013</div><div class="rr-where">Maastricht</div><div class="rr-what">M.Sc., Maastricht University; Forschungspraktikum am Donders Institute, Nijmegen</div>'),
    ('<div class="rr-when rr-num">2014 to 2022</div><div class="rr-where">Munich</div><div class="rr-what">Ph.D. and postdoctoral research, LMU Munich</div>',
     '<div class="rr-when rr-num">2014 a 2022</div><div class="rr-where">Múnich</div><div class="rr-what">Doctorado e investigación posdoctoral, LMU Múnich</div>',
     '<div class="rr-when rr-num">2014 bis 2022</div><div class="rr-where">München</div><div class="rr-what">Promotion und Postdoc-Forschung, LMU München</div>'),
    ('<div class="rr-when rr-num">2019 to 2021</div><div class="rr-where">Detroit</div><div class="rr-what">Postdoctoral fellow, Institute of Gerontology, Wayne State University</div>',
     '<div class="rr-when rr-num">2019 a 2021</div><div class="rr-where">Detroit</div><div class="rr-what">Investigadora posdoctoral, Instituto de Gerontología, Wayne State University</div>',
     '<div class="rr-when rr-num">2019 bis 2021</div><div class="rr-where">Detroit</div><div class="rr-what">Postdoktorandin, Institute of Gerontology, Wayne State University</div>'),
    ('<div class="rr-when rr-num">Since 2022</div><div class="rr-where">Jena</div><div class="rr-what">Department of Neurology, Jena University Hospital</div>',
     '<div class="rr-when rr-num">Desde 2022</div><div class="rr-where">Jena</div><div class="rr-what">Departamento de Neurología, Hospital Universitario de Jena</div>',
     '<div class="rr-when rr-num">Seit 2022</div><div class="rr-where">Jena</div><div class="rr-what">Klinik für Neurologie, Universitätsklinikum Jena</div>'),
    ("[Full career, awards, and teaching](about.qmd){.rr-more}", "[Trayectoria completa, premios y docencia](about.qmd){.rr-more}", "[Vollständiger Werdegang, Auszeichnungen und Lehre](about.qmd){.rr-more}"),
    ("[Collaboration]{.rr-eyebrow}", "[Colaboración]{.rr-eyebrow}", "[Zusammenarbeit]{.rr-eyebrow}"),
    ("## Points of connection", "## Puntos de encuentro", "## Anknüpfungspunkte"),
    ("Adriana's expertise spans theory-based cognitive assessment, multimodal neuroimaging, and statistical modeling in aging and clinical populations. Researchers, institutions, and R&D teams working on related questions are welcome to get in touch.",
     "La experiencia de Adriana abarca la evaluación cognitiva basada en teoría, la neuroimagen multimodal y la modelización estadística en el envejecimiento y en poblaciones clínicas. Investigadores, instituciones y equipos de I+D que trabajen en preguntas afines pueden ponerse en contacto.",
     "Adrianas Expertise umfasst theoriebasierte kognitive Diagnostik, multimodale Bildgebung und statistische Modellierung bei älteren Menschen und klinischen Gruppen. Forschende, Institutionen und F&E-Teams mit verwandten Fragestellungen sind eingeladen, Kontakt aufzunehmen."),
    ("[Methods and expertise](expertise.qmd){.rr-btn .rr-btn-secondary}", "[Métodos y experiencia](expertise.qmd){.rr-btn .rr-btn-secondary}", "[Methoden und Expertise](expertise.qmd){.rr-btn .rr-btn-secondary}"),
    ("- Multimodal MRI analysis [Resting-state, diffusion, and task fMRI]{}", "- Análisis de resonancia magnética multimodal [En reposo, de difusión y con tareas]{}", "- Multimodale MRT-Analyse [Ruhezustands-, Diffusions- und aufgabenbasierte fMRT]{}"),
    ("- Theory-based assessment of visual attention [Processing speed, short-term memory capacity, alertness]{}",
     "- Evaluación de la atención visual basada en teoría [Velocidad de procesamiento, capacidad de la memoria a corto plazo, alerta]{}",
     "- Theoriebasierte Erfassung visueller Aufmerksamkeit [Verarbeitungsgeschwindigkeit, Kurzzeitgedächtniskapazität, Alertness]{}"),
    ("- Longitudinal and intervention designs [Latent growth curve models, randomized controlled trials]{}",
     "- Diseños longitudinales y de intervención [Modelos de curva de crecimiento latente, ensayos controlados aleatorizados]{}",
     "- Längsschnitt- und Interventionsdesigns [Latente Wachstumskurvenmodelle, randomisierte kontrollierte Studien]{}"),
    ("- Applied machine learning [Clinical imaging and open social data]{}", "- Aprendizaje automático aplicado [Neuroimagen clínica y datos sociales abiertos]{}", "- Angewandtes Machine Learning [Klinische Bildgebung und offene Sozialdaten]{}"),
    ("[Competitive fellowships]{.rr-eyebrow}", "[Becas competitivas]{.rr-eyebrow}", "[Kompetitive Stipendien]{.rr-eyebrow}"),
    ("## Marie Skłodowska-Curie support at two career stages", "## Apoyo Marie Skłodowska-Curie en dos etapas de su carrera", "## Marie-Skłodowska-Curie-Förderung in zwei Karrierephasen"),
    ("Adriana's doctoral and postdoctoral research were each funded through highly competitive fellowship programs co-funded by the European Union's Marie Skłodowska-Curie Actions.",
     "La investigación doctoral y la posdoctoral de Adriana se financiaron, cada una, mediante programas de becas muy competitivos cofinanciados por las Acciones Marie Skłodowska-Curie de la Unión Europea.",
     "Adrianas Promotions- und Postdoc-Forschung wurde jeweils über hochkompetitive Stipendienprogramme gefördert, die von den Marie-Skłodowska-Curie-Maßnahmen der Europäischen Union kofinanziert wurden."),
    ("[Funding and awards](about.qmd#funding-heading){.rr-more}", "[Financiación y premios](about.qmd#funding-heading){.rr-more}", "[Förderung und Auszeichnungen](about.qmd#funding-heading){.rr-more}"),
    ("[Research supported by]{.rr-eyebrow}", "[Investigación financiada por]{.rr-eyebrow}", "[Forschung gefördert von]{.rr-eyebrow}"),
]

# English words that must not survive in a translated homepage outside code, data and names.
LEFTOVER_CHECK = ["Read more", "Explore the research", "Representative work", "Why it matters", "Get in touch"]


def main() -> int:
    src = (ROOT / "index.qmd").read_text(encoding="utf-8")
    for col, lang in ((1, "es"), (2, "de")):
        out = src
        for row in STRINGS:
            english, expected = row[0], (row[3] if len(row) > 3 else 1)
            n = src.count(english)
            if n != expected:
                raise SystemExit(f"translate_index: {english[:70]!r} occurs {n} times in index.qmd, expected {expected}; "
                                 "update scripts/translate_index.py")
            out = out.replace(english, row[col])
        left = [w for w in LEFTOVER_CHECK if w in out]
        if left:
            raise SystemExit(f"translate_index: English left in index.{lang}.qmd: {left}")
        (ROOT / f"index.{lang}.qmd").write_text(out, encoding="utf-8")
        print(f"  index.{lang}.qmd written ({len(STRINGS)} strings)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
