"""English / French / Spanish texts for the poster. Every default fits its character limit."""
import datetime as _dt

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre",
           "octobre", "novembre", "décembre"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"],
}

T = {
    "en": dict(
        labels=dict(methodology="Methodology", more_info="For More Information", email="E-mail:",
                    website="Website:", no_data="No data", date="Date"),
        headings=dict(key_figures="Key figures", key_messages="Key messages"),
        title=dict(flood="Flood exposure overview", earthquake="Earthquake exposure overview",
                   admin="Exposure overview"),
        kf_label="People exposed",
        kf_note=dict(flood="People living in flooded areas.",
                     earthquake="People in areas of intensity {thr} or higher.",
                     admin="People living in the selected areas."),
        ind=dict(area_flood="Flooded area", area_eq="Area at intensity {thr}+", area_admin="Area of selected units",
                 nbuildings="Buildings exposed", buildings_area="Building area exposed",
                 roads_length="Roads exposed", elegrid_length="Electricity network exposed",
                 econ="Economic damage", idps="Forecasted IDPs"),
        legend_flood="Flooded area", epicentre="Epicentre", ramp_title="Intensity (MMI)",
        vul_title="Population in multidimensional poverty",
        vul_caption="Share of people who are multidimensionally poor in the affected areas.",
        grp_title="Population exposed (composition) %", grp_title_eq="Population exposed by intensity (%)",
        grp_note="Percentages of the exposed population.", grp_note_eq="Share of exposed people per intensity class.",
        groups=dict(child_total="Children", elderly_total="Elderly", female_total="Women", male_total="Men",
                    active_total="Adults"),
        disclaimer=("Preliminary analysis based on remotely sensed and geospatial data. Results show estimated "
                    "exposure and should be read alongside field assessments as more information becomes available."),
        and_="and", event_date="Event date: ",
    ),
    "fr": dict(
        labels=dict(methodology="Méthodologie", more_info="Pour plus d'informations", email="Courriel :",
                    website="Site web :", no_data="Pas de données", date="Date"),
        headings=dict(key_figures="Chiffres clés", key_messages="Messages clés"),
        title=dict(flood="Exposition aux inondations", earthquake="Exposition au séisme",
                   admin="Aperçu de l'exposition"),
        kf_label="Personnes exposées",
        kf_note=dict(flood="Personnes vivant dans les zones inondées.",
                     earthquake="Personnes en zone d'intensité {thr} ou plus.",
                     admin="Personnes vivant dans les zones choisies."),
        ind=dict(area_flood="Zone inondée", area_eq="Zone d'intensité {thr}+", area_admin="Superficie des unités",
                 nbuildings="Bâtiments exposés", buildings_area="Surface bâtie exposée",
                 roads_length="Routes exposées", elegrid_length="Réseau électrique exposé",
                 econ="Dommages économiques", idps="PDI prévues"),
        legend_flood="Zone inondée", epicentre="Épicentre", ramp_title="Intensité (MMI)",
        vul_title="Pauvreté multidimensionnelle",
        vul_caption="Part des personnes en pauvreté multidimensionnelle dans les zones touchées.",
        grp_title="Population exposée (composition) %", grp_title_eq="Population exposée par intensité (%)",
        grp_note="Pourcentages de la population exposée.", grp_note_eq="Part des personnes exposées par classe d'intensité.",
        groups=dict(child_total="Enfants", elderly_total="Âgés", female_total="Femmes", male_total="Hommes",
                    active_total="Adultes"),
        disclaimer=("Analyse préliminaire fondée sur la télédétection et des données géospatiales. Les résultats "
                    "estiment l'exposition et doivent être lus avec les évaluations de terrain."),
        and_="et", event_date="Date de l'événement : ",
    ),
    "es": dict(
        labels=dict(methodology="Metodología", more_info="Para más información", email="Correo:",
                    website="Sitio web:", no_data="Sin datos", date="Fecha"),
        headings=dict(key_figures="Cifras clave", key_messages="Mensajes clave"),
        title=dict(flood="Exposición a inundaciones", earthquake="Exposición al terremoto",
                   admin="Resumen de exposición"),
        kf_label="Personas expuestas",
        kf_note=dict(flood="Personas que viven en zonas inundadas.",
                     earthquake="Personas en zonas de intensidad {thr} o más.",
                     admin="Personas en las zonas seleccionadas."),
        ind=dict(area_flood="Área inundada", area_eq="Área con intensidad {thr}+", area_admin="Área de las unidades",
                 nbuildings="Edificios expuestos", buildings_area="Superficie construida",
                 roads_length="Carreteras expuestas", elegrid_length="Red eléctrica expuesta",
                 econ="Daños económicos", idps="Desplazados previstos"),
        legend_flood="Zona inundada", epicentre="Epicentro", ramp_title="Intensidad (MMI)",
        vul_title="Población en pobreza multidimensional",
        vul_caption="Proporción de personas en pobreza multidimensional en las zonas afectadas.",
        grp_title="Población expuesta (composición) %", grp_title_eq="Población expuesta por intensidad (%)",
        grp_note="Porcentajes de la población expuesta.", grp_note_eq="Proporción de personas expuestas por clase de intensidad.",
        groups=dict(child_total="Niños", elderly_total="Mayores", female_total="Mujeres", male_total="Hombres",
                    active_total="Adultos"),
        disclaimer=("Análisis preliminar basado en teledetección y datos geoespaciales. Los resultados estiman la "
                    "exposición y deben leerse junto con las evaluaciones de campo."),
        and_="y", event_date="Fecha del evento: ",
    ),
}

# Phrases built from the admin-level name the user types (plural) and its grammatical gender (FR/ES)
_PHRASES = {
    "chip": {"en": "Map of affected {pl}", "fr": {"m": "Carte des {pl} touchés", "f": "Carte des {pl} touchées"},
             "es": {"m": "Mapa de {pl} afectados", "f": "Mapa de {pl} afectadas"}},
    "chip_admin": {"en": "Map of selected {pl}", "fr": {"m": "Carte des {pl} retenus", "f": "Carte des {pl} retenues"},
                   "es": {"m": "Mapa de {pl} elegidos", "f": "Mapa de {pl} elegidas"}},
    "affected": {"en": "Affected {pl}", "fr": {"m": "{Pl} touchés", "f": "{Pl} touchées"},
                 "es": {"m": "{Pl} afectados", "f": "{Pl} afectadas"}},
    "selected": {"en": "Selected {pl}", "fr": {"m": "{Pl} retenus", "f": "{Pl} retenues"},
                 "es": {"m": "{Pl} elegidos", "f": "{Pl} elegidas"}},
}


def phrase(key, lang, plural, gender="m"):
    p = _PHRASES[key][lang]
    if isinstance(p, dict):
        p = p.get(gender, p["m"])
    pl = plural.strip()
    return p.format(pl=pl.lower(), Pl=pl[:1].upper() + pl[1:])


def t(lang, key, sub=None):
    v = T[lang][key]
    return v[sub] if sub else v


def join_list(items, lang):
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {T[lang]['and_']} " + items[-1]


def long_date(d, lang):
    if isinstance(d, str):
        d = _dt.date.fromisoformat(d[:10])
    if lang == "en":
        return f"{d.day} {MONTHS['en'][d.month - 1]} {d.year}"
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def fmt_int(v, lang):
    s = f"{round(v):,}"
    return s.replace(",", "\u202f" if lang == "fr" else "." if lang == "es" else ",")


def roman(c):
    from .config import ROMAN
    return ROMAN.get(int(c), str(c))


# ---------------- drafted texts (user edits them in the app) ----------------
DATASET_NAMES = {
    "population": "WorldPop", "buildings": "Google–Microsoft–OSM open buildings", "roads": "OpenStreetMap roads",
    "elegrid": "the World Bank electricity grid", "deprivation": "the GRDI deprivation index (CIESIN)",
    "rwi": "the Relative Wealth Index (Meta)", "gdp": "gridded GDP", "landuse": "Sentinel-2 land use",
}


def draft_methodology(lang, crisis, hazard_source, admin_source, components, thr=None):
    ds = join_list([DATASET_NAMES.get(c, c) for c in components], "en")
    if lang == "en":
        haz = {"flood": f"Flood extent: {hazard_source}.",
               "earthquake": f"Shaking intensity: {hazard_source}, grouped into whole MMI classes; areas of intensity {thr} or higher are counted as affected.",
               "admin": "Affected area: administrative units selected by the analyst."}[crisis]
        return (f"{haz} Administrative boundaries: {admin_source}. Exposure was estimated with UNDP RAPIDA by "
                f"overlaying the affected areas with {ds}. Figures are estimates of exposure, not of damage or impact.")
    if lang == "fr":
        haz = {"flood": f"Étendue de l'inondation : {hazard_source}.",
               "earthquake": f"Intensité des secousses : {hazard_source}, regroupée en classes MMI entières ; les zones d'intensité {thr} ou plus sont comptées comme touchées.",
               "admin": "Zone touchée : unités administratives choisies par l'analyste."}[crisis]
        return (f"{haz} Limites administratives : {admin_source}. L'exposition a été estimée avec UNDP RAPIDA en "
                f"croisant les zones touchées avec {ds}. Les chiffres estiment l'exposition, pas les dommages ni l'impact.")
    haz = {"flood": f"Extensión de la inundación: {hazard_source}.",
           "earthquake": f"Intensidad del sismo: {hazard_source}, agrupada en clases MMI enteras; las zonas de intensidad {thr} o más se cuentan como afectadas.",
           "admin": "Zona afectada: unidades administrativas seleccionadas por el analista."}[crisis]
    return (f"{haz} Límites administrativos: {admin_source}. La exposición se estimó con UNDP RAPIDA cruzando las "
            f"zonas afectadas con {ds}. Las cifras estiman la exposición, no los daños ni el impacto.")


def draft_key_messages(lang, crisis, S):
    """S: dict of formatted values that may be None: pop, bld, roads, elec, regions, mag, thr, date, n_units, plural."""
    def ok(*k):
        return all(S.get(x) for x in k)
    m = []
    if lang == "en":
        if crisis == "earthquake" and ok("mag"):
            m.append(("alert", f"A magnitude {S['mag']} earthquake struck {S.get('regions') or 'the area'}"
                               f"{' on ' + S['date'] if S.get('date') else ''}."))
        if ok("pop"):
            what = {"flood": "live in flooded areas", "earthquake": f"live where shaking reached intensity {S.get('thr')} or more",
                    "admin": "live in the selected areas"}[crisis]
            m.append(("flood" if crisis == "flood" else "alert", f"An estimated {S['pop']} people {what}"
                      + (f", across {S['n_units']} {S['plural']}." if ok("n_units", "plural") else ".")))
        if ok("bld"):
            infra = f"{S['bld']} buildings"
            if ok("roads"):
                infra += f", {S['roads']} km of roads"
            if ok("elec"):
                infra += f" and {S['elec']} km of power lines"
            m.append(("alert", f"{infra} are exposed."))
        m.append(("analysis", "Satellite-based analysis shows where the hazard meets people and assets, "
                              "giving a first picture of early recovery priorities."))
    elif lang == "fr":
        if crisis == "earthquake" and ok("mag"):
            m.append(("alert", f"Un séisme de magnitude {S['mag']} a frappé {S.get('regions') or 'la zone'}"
                               f"{' le ' + S['date'] if S.get('date') else ''}."))
        if ok("pop"):
            what = {"flood": "vivent dans des zones inondées", "earthquake": f"vivent là où l'intensité a atteint {S.get('thr')} ou plus",
                    "admin": "vivent dans les zones choisies"}[crisis]
            m.append(("flood" if crisis == "flood" else "alert", f"Environ {S['pop']} personnes {what}"
                      + (f", dans {S['n_units']} {S['plural']}." if ok("n_units", "plural") else ".")))
        if ok("bld"):
            infra = f"{S['bld']} bâtiments"
            if ok("roads"):
                infra += f", {S['roads']} km de routes"
            if ok("elec"):
                infra += f" et {S['elec']} km de lignes électriques"
            m.append(("alert", f"{infra} sont exposés."))
        m.append(("analysis", "L'analyse satellitaire montre où l'aléa touche la population et les biens : "
                              "une première image des priorités de relèvement."))
    else:
        if crisis == "earthquake" and ok("mag"):
            m.append(("alert", f"Un terremoto de magnitud {S['mag']} afectó {S.get('regions') or 'la zona'}"
                               f"{' el ' + S['date'] if S.get('date') else ''}."))
        if ok("pop"):
            what = {"flood": "viven en zonas inundadas", "earthquake": f"viven donde la intensidad llegó a {S.get('thr')} o más",
                    "admin": "viven en las zonas seleccionadas"}[crisis]
            m.append(("flood" if crisis == "flood" else "alert", f"Se estima que {S['pop']} personas {what}"
                      + (f", en {S['n_units']} {S['plural']}." if ok("n_units", "plural") else ".")))
        if ok("bld"):
            infra = f"{S['bld']} edificios"
            if ok("roads"):
                infra += f", {S['roads']} km de carreteras"
            if ok("elec"):
                infra += f" y {S['elec']} km de red eléctrica"
            m.append(("alert", f"{infra} están expuestos."))
        m.append(("analysis", "El análisis satelital muestra dónde la amenaza alcanza a personas y bienes: "
                              "una primera imagen de las prioridades de recuperación."))
    return m[:3]


def draft_narrative(lang, crisis, S):
    if lang == "en":
        return (f"This one-pager summarises the estimated exposure of people, buildings and infrastructure in "
                f"{S.get('regions') or 'the affected area'}. Figures come from an overlay of the hazard footprint with "
                f"global datasets and should be updated as field information becomes available.")
    if lang == "fr":
        return (f"Cette fiche résume l'exposition estimée de la population, des bâtiments et des infrastructures en "
                f"{S.get('regions') or 'zone touchée'}. Les chiffres proviennent du croisement de l'empreinte de l'aléa avec "
                f"des données mondiales et seront mis à jour avec les informations de terrain.")
    return (f"Esta ficha resume la exposición estimada de la población, los edificios y la infraestructura en "
            f"{S.get('regions') or 'la zona afectada'}. Las cifras provienen del cruce de la huella de la amenaza con "
            f"datos mundiales y se actualizarán con la información de campo.")


def composition_line(lang, items):
    """'Children 47% · Elderly 3% · Women 51% of exposed people.' (fits the 100-character note)."""
    pct = (lambda v: f"{v:.0f}\u202f%") if lang == "fr" else (lambda v: f"{v:.0f}%")
    tail = {"en": " of exposed people.", "fr": " des personnes exposées.", "es": " de las personas expuestas."}[lang]
    return " · ".join(f"{lab} {pct(v)}" for lab, v in items) + tail
