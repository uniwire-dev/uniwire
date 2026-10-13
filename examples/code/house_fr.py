"""Maison T4 (NF C 15-100) : exemple uniwire « schéma as code », libellés en français.

Lancer : ``python house_fr.py`` (depuis n'importe quel dossier) → écrit ``house_fr.uniwire.json`` et
``house_fr.pdf`` dans le dossier courant.
"""

from uniwire.build import *

# Modèles de protections (Template = jeu de mots-clés réutilisable)
DISJ = Template(icn_kA=4.5, poles="1P+N", product={"manufacturer": "Hager", "range": "MJN / MJT"})
ID_AC = Template(poles="2P", product={"manufacturer": "Hager", "range": "CDC interrupteur différentiel type AC"})
ID_A = Template(poles="2P", product={"manufacturer": "Hager", "range": "CDA interrupteur différentiel type A"})

with Installation("Maison exemple : tableau de logement T4 avec borne de recharge", earthing="TT", system="1P+N",
                  un="230 V", profiles=["nfc15100"], lang="fr", project="EX-C1", author="uniwire examples",
                  supply="Tarif Bleu", subscribed_kVA=12, surface_m2=110,
                  earth_resistance_ohm=35, standard="NF C 15-100",
                  notes=["Démontre l'API Python : Template, boucles de circuits, opérateur >>, liens control",
                         "Borne VE mode 3 7,4 kW : ID 30 mA type F, détection 6 mA DC intégrée à la borne (RDC-DD)"]) as inst:
    with Grid("Réseau public", supply="Tarif Bleu 12 kVA"), \
            Meter("-P0", label="Compteur Linky", kind="Linky"), \
            MainBreaker("-Q0", "15-60 A", "500 mA", selective=True, subscribed_kVA=12, label="AGCP"), \
            Board("TD1", label="Tableau de logement", kind="main", ways=52):

        Breaker("-F0", "C20", label="Parafoudre", **DISJ) >> SPD("-F01", type="2", imax_kA=20, up_kV=1.5)

        # 30 mA type AC : éclairage, prises, volets (max 8 circuits par interrupteur différentiel)
        with RCD("-Q1", "40 A", "30 mA", type="AC", **ID_AC):
            for i, (piece, pts) in enumerate([("Éclairage séjour / cuisine", 8), ("Éclairage chambres", 6),
                                              ("Éclairage extérieur", 3)], start=1):
                Breaker(f"-Q1{i}", "C16", cable="3G1,5", **DISJ) >> Lighting(piece, points=pts)
            for i, (piece, pts) in enumerate([("Prises séjour", 8), ("Prises chambres 1-2", 10),
                                              ("Prises chambre 3 / bureau", 7)], start=4):
                Breaker(f"-Q1{i}", "C20", cable="3G2,5", **DISJ) >> Socket(piece, points=pts)
            Breaker("-Q17", "C16", cable="3G1,5", **DISJ) >> Shutter("Volets roulants")

        # 30 mA type A : circuits spécialisés
        with RCD("-Q2", "40 A", "30 mA", type="A", **ID_A):
            Breaker("-Q21", "C20", cable="3G2,5", **DISJ) >> Appliance("Lave-linge", kind="washing_machine")
            Breaker("-Q22", "C20", cable="3G2,5", **DISJ) >> Appliance("Sèche-linge", kind="dryer")
            Breaker("-Q23", "C20", cable="3G2,5", **DISJ) >> Appliance("Lave-vaisselle", kind="dishwasher")
            Breaker("-Q24", "C32", cable="3G6", **DISJ) >> Cooking("Plaque de cuisson", kind="hob", p="7,2 kW")
            Breaker("-Q25", "C20", cable="3G2,5", **DISJ) >> Cooking("Four", kind="oven", p="3,5 kW")
            Breaker("-Q26", "C20", cable="3G2,5", **DISJ) >> Appliance("Congélateur", kind="freezer")

        # Gestionnaire d'énergie : délestage de la borne et du chauffe-eau
        ems = Breaker("-Q5", "C2", **DISJ) >> Controller("-A1", label="Délesteur", function="délesteur",
                                                            symbol_text="EMS")

        # 30 mA type AC : chauffe-eau heures creuses et chauffage (fil pilote)
        with RCD("-Q3", "63 A", "30 mA", type="AC", **ID_AC):
            hc = Breaker("-Q31", "C20", cable="3G2,5", **DISJ) >> Contactor("-KM1", "20 A", function="HC", coil_V=230)
            hc >> WaterHeater("Chauffe-eau 200 L", volume_L=200, p="2,4 kW")
            for i, (piece, kw) in enumerate([("Radiateurs séjour", 4.0), ("Radiateurs chambres", 3.0),
                                             ("Sèche-serviettes SdB", 1.0)], start=2):
                Breaker(f"-Q3{i}", "C20", cable="3G2,5", **DISJ) >> Heating(piece, p=kw, pilot_wire=True)

        # Borne de recharge : circuit dédié, ID type F
        with RCD("-Q4", "40 A", "30 mA", type="F", **ID_A):
            Breaker("-Q41", "C32", cable="U1000R2V 3G6 18 m", **DISJ) >> EVCharger("Borne VE 7,4 kW", mode="3", p="7,4 kW")

    control(ems, hc, "Délestage")

    inst.view(id="sld", paper="A3", cartouche=["label", "ref", "protection", "idn_mA", "rcd_type", "cable", "points", "p_kW"])

if __name__ == "__main__":
    findings = inst.check()
    for f in findings:
        print(f)
    inst.save("house_fr.uniwire.json")
    print(inst.render("house_fr.pdf"))
