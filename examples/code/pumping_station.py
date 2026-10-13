"""Pumping station with a WAGO PFC200: uniwire "schematics as code" example."""

from uniwire.build import *

MOT = Template(curve="D", icn_kA=10, poles="3P", product={"manufacturer": "Schneider Electric", "range": "Acti9 iC60N"})
KM = Template(coil_V=230, poles="3P", product={"manufacturer": "Schneider Electric", "range": "TeSys Deca"})

with Installation("Pumping station: process board with WAGO PFC200", earthing="TN-S", system="3P+N", un="400 V",
                  project="EX-51", lang="en") as inst:
    with Grid("Main LV board", un="400 V"), Board("TD-PR", label="Pumping process", in_A=63, system="3P+N"):
        with SwitchDisconnector("-Q0", "63 A", poles="4P", label="Main switch"):
            with Breaker("-Q10", "C2", poles="1P+N", label="24 V supply"):
                with PowerSupply("-T1", u1="230 V", u2="24 V", output="DC", in_A=5, product="WAGO Eco"):
                    api = PLC("-A1", label="Pump controller", family="PFC200", role="controller",
                              protocols=["Modbus TCP"], product="WAGO 750-8212")
                    api.add("power_feed", "750-602", un_V=24)
                    api.add("di", "750-430", channels=8, channel_labels={"1": "High level", "2": "Low level"})
                    api.add("do", "750-530", channels=8, rating_A=0.5)
                    relays = api.add("relay_out", "750-512", channels=2, rating_A=2)
                    api.add("power_measurement", "750-494", channels=3)
                    api.add("end", "750-600")
            pumps = []
            for i in (1, 2):
                km = Breaker(f"-Q2{i}", "D16", cable="4G2,5 25 m", **MOT) >> Contactor(f"-KM2{i}", "18 A", **KM)
                km >> Motor(f"Pump {i}", p="5.5 kW")
                control(relays[i], km, f"Pump {i}")
            with Breaker("-Q30", "C10", poles="1P+N", cable="3G1,5 60 m", label="Lift station"):
                rio = PLC("-A2", label="Remote I/O", role="coupler", protocols=["Modbus TCP"], product="WAGO 750-362")
                rio.add("power_feed", "750-602", un_V=24)
                rio.add("ai", "750-454", channels=2, signal="4-20 mA")
                rio.add("end", "750-600")
    data(rio, api, protocol="Modbus TCP")

if __name__ == "__main__":
    for f in inst.check():
        print(f)
    inst.save("pumping_station.uniwire.json")
    print(inst.render("pumping_station.pdf"))
