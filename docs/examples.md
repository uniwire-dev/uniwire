# Examples

The [`examples/`](https://github.com/uniwire-dev/uniwire/tree/main/examples) folder of the repository holds
53 complete `*.uniwire.json` documents (some are built with the
[code-first API](build.md) from a script in `examples/code/`), validated against the schema and rendered
by the continuous integration. Open any of them in the [web viewer](https://uniwire.sh/viewer/).

| # | Example | Lang | Earthing | System | Sheets |
|---|---|---|---|---|---|
| 01 | [Studio 28 m² : tableau de répartition](https://github.com/uniwire-dev/uniwire/blob/main/examples/01_studio_apartment.uniwire.json) | fr | TT | 1P+N | 1 |
| 02 | [Maison T4 : tableau de répartition monophasé](https://github.com/uniwire-dev/uniwire/blob/main/examples/02_house_3_bedrooms_tt.uniwire.json) | fr | TT | 1P+N | 1 |
| 03 | [Grande maison triphasée : PAC air/eau et borne de recharge](https://github.com/uniwire-dev/uniwire/blob/main/examples/03_house_three_phase_heat_pump_ev.uniwire.json) | fr | TT | 3P+N | 2 |
| 04 | [Semi-detached house: all-RCBO consumer unit](https://github.com/uniwire-dev/uniwire/blob/main/examples/04_uk_consumer_unit_rcbo.uniwire.json) | en | TN-C-S | 1P+N | 1 |
| 05 | [Single-family home: 200 A main breaker load center](https://github.com/uniwire-dev/uniwire/blob/main/examples/05_us_residential_200a_panel.uniwire.json) | en | TN-C-S | split-phase | 1 |
| 06 | [Single-family house (Germany): meter cabinet and distribution board](https://github.com/uniwire-dev/uniwire/blob/main/examples/06_german_single_family_house.uniwire.json) | en | TN-C-S | 3P+N | 1 |
| 07 | [Apartment building: 12 dwellings, meter room and common services](https://github.com/uniwire-dev/uniwire/blob/main/examples/07_apartment_building_risers.uniwire.json) | en | TN-C-S | 3P+N | 5 |
| 08 | [Small retail shop: distribution board](https://github.com/uniwire-dev/uniwire/blob/main/examples/08_small_retail_shop.uniwire.json) | en | TN-S | 3P+N | 1 |
| 09 | [Boulangerie-pâtisserie : tableau général triphasé](https://github.com/uniwire-dev/uniwire/blob/main/examples/09_bakery_three_phase.uniwire.json) | fr | TT | 3P+N | 1 |
| 10 | [Holiday cottage: standby generator with manual changeover](https://github.com/uniwire-dev/uniwire/blob/main/examples/10_holiday_cottage_generator.uniwire.json) | en | TT | 1P+N | 1 |
| 11 | [Off-grid tiny house: PV, 48 V battery and inverter/charger](https://github.com/uniwire-dev/uniwire/blob/main/examples/11_tiny_house_off_grid_pv.uniwire.json) | en | TN-S | 1P+N | 1 |
| 12 | [Detached garage workshop: sub-board with motor circuits](https://github.com/uniwire-dev/uniwire/blob/main/examples/12_garage_workshop_motors.uniwire.json) | en | TN-C-S | 3P+N | 1 |
| 13 | [Piscine privée : coffret du local technique](https://github.com/uniwire-dev/uniwire/blob/main/examples/13_swimming_pool_equipment.uniwire.json) | fr | TT | 1P+N | 1 |
| 14 | [Farmhouse and dairy barn: long buried feeder](https://github.com/uniwire-dev/uniwire/blob/main/examples/14_farmhouse_barn_long_feeder.uniwire.json) | en | TT | 3P+N | 2 |
| 15 | [Maison tout électrique : télérupteurs et délestage](https://github.com/uniwire-dev/uniwire/blob/main/examples/15_smart_home_load_shedding.uniwire.json) | fr | TT | 1P+N | 1 |
| 16 | [Dental practice: main board and UPS-backed circuits](https://github.com/uniwire-dev/uniwire/blob/main/examples/16_dental_practice_ups.uniwire.json) | en | TN-S | 3P+N | 1 |
| 17 | [Hair salon: 230 V IT three-phase board (Nordic style)](https://github.com/uniwire-dev/uniwire/blob/main/examples/17_hair_salon_it_230v.uniwire.json) | en | IT | 3P | 1 |
| 18 | [Office building (3 floors): main LV switchboard and floor distribution boards](https://github.com/uniwire-dev/uniwire/blob/main/examples/18_office_building_main_lv_switchboard.uniwire.json) | en | TN-C-S | 3P+N | 5 |
| 19 | [École élémentaire : TGBT et tableaux divisionnaires](https://github.com/uniwire-dev/uniwire/blob/main/examples/19_ecole_tgbt_td.uniwire.json) | fr | TT | 3P+N | 4 |
| 20 | [Hotel (120 rooms): main LV board and kitchen distribution board](https://github.com/uniwire-dev/uniwire/blob/main/examples/20_hotel_kitchen_board.uniwire.json) | en | TN-S | 3P+N | 2 |
| 21 | [Supermarket (2 500 m² sales area): refrigeration plant and HVAC with load shedding](https://github.com/uniwire-dev/uniwire/blob/main/examples/21_supermarket_refrigeration_hvac.uniwire.json) | en | TN-S | 3P+N | 2 |
| 22 | [Aile hospitalière : tableau du bloc opératoire avec IT médical](https://github.com/uniwire-dev/uniwire/blob/main/examples/22_bloc_operatoire_it_medical.uniwire.json) | fr | TN-S | 3P+N | 1 |
| 23 | [Server room (12 racks): 2N UPS, maintenance bypass, redundant PDUs A/B](https://github.com/uniwire-dev/uniwire/blob/main/examples/23_server_room_ups_2n.uniwire.json) | en | TN-S | 3P+N | 1 |
| 24 | [Plastics factory: motor control centre MCC-2 (extrusion line)](https://github.com/uniwire-dev/uniwire/blob/main/examples/24_factory_mcc_motor_starters.uniwire.json) | en | TN-S | 3P | 1 |
| 25 | [Poste HTA/BT 20 kV / 410 V : 1000 kVA, comptage BT, TGBT](https://github.com/uniwire-dev/uniwire/blob/main/examples/25_poste_hta_bt_1000kva.uniwire.json) | fr | TN-S | 3P+N | 1 |
| 26 | [Distribution centre: two 1250 kVA transformers with bus-section coupler and 2-of-3 interlock](https://github.com/uniwire-dev/uniwire/blob/main/examples/26_two_transformers_bus_tie.uniwire.json) | en | TN-S | 3P+N | 1 |
| 27 | [Medical centre: standby generator, automatic transfer switch and load shedding](https://github.com/uniwire-dev/uniwire/blob/main/examples/27_standby_generator_ats_load_shedding.uniwire.json) | en | TN-C-S | 3P+N | 1 |
| 28 | [Gymnase : tableau éclairage sportif par niveaux et commande par automate LOGO!](https://github.com/uniwire-dev/uniwire/blob/main/examples/28_gymnase_eclairage_sportif.uniwire.json) | fr | TT | 3P+N | 1 |
| 29 | [Underground car park (3 levels, 420 spaces): ventilation, smoke control and fire-safety supplies](https://github.com/uniwire-dev/uniwire/blob/main/examples/29_car_park_ventilation_fire_safety.uniwire.json) | en | TN-S | 3P+N | 1 |
| 30 | [Station de traitement d'eau potable 300 m³/h : poste, TGBT en schéma IT et tableau process](https://github.com/uniwire-dev/uniwire/blob/main/examples/30_station_traitement_eau_it.uniwire.json) | fr | IT | 3P | 2 |
| 31 | [Warehouse (6 000 m²): dock doors, forklift charging and high-bay lighting trunking](https://github.com/uniwire-dev/uniwire/blob/main/examples/31_warehouse_docks_forklift_charging.uniwire.json) | en | TT | 3P+N | 3 |
| 32 | [Retail store (US): 480Y/277 V service, 75 kVA step-down to 208Y/120 V](https://github.com/uniwire-dev/uniwire/blob/main/examples/32_us_retail_480y277_stepdown.uniwire.json) | en | TN-C-S | 3P+N | 3 |
| 33 | [Machining workshop: energy metering with CTs, power meters and Modbus gateway](https://github.com/uniwire-dev/uniwire/blob/main/examples/33_workshop_metering_cts.uniwire.json) | en | TN-C | 3P+N | 1 |
| 34 | [Chantier de construction : branchement provisoire et distribution de chantier](https://github.com/uniwire-dev/uniwire/blob/main/examples/34_chantier_distribution_provisoire.uniwire.json) | fr | TT | 3P+N | 1 |
| 35 | [Maison exemple : autoconsommation PV 6 kWc avec onduleur string](https://github.com/uniwire-dev/uniwire/blob/main/examples/35_pv_selfconsumption_string_fr.uniwire.json) | fr | TT | 1P+N | 1 |
| 36 | [Maison exemple : PV 4 kWc à micro-onduleurs et batterie couplée AC](https://github.com/uniwire-dev/uniwire/blob/main/examples/36_pv_microinverters_ac_battery_fr.uniwire.json) | fr | TT | 1P+N | 1 |
| 37 | [Warehouse rooftop PV plant 100 kWp: LV connection](https://github.com/uniwire-dev/uniwire/blob/main/examples/37_rooftop_pv_100kwp.uniwire.json) | en | TN-C-S | 3P+N | 1 |
| 38 | [Ground-mounted PV farm 2.5 MWp: LV AC and DC system](https://github.com/uniwire-dev/uniwire/blob/main/examples/38_pv_farm_lv_combiners.uniwire.json) | en | IT | 3P | 5 |
| 39 | [Example House: hybrid inverter, battery and protected loads panel (120/240 V)](https://github.com/uniwire-dev/uniwire/blob/main/examples/39_hybrid_inverter_backup_us.uniwire.json) | en | TN-C-S | split-phase | 1 |
| 40 | [EV charging hub: 8 x 22 kW with dynamic load management](https://github.com/uniwire-dev/uniwire/blob/main/examples/40_ev_charging_hub_load_management.uniwire.json) | en | TN-S | 3P+N | 1 |
| 41 | [Battery storage container 250 kW / 500 kWh with 380 V DC microgrid](https://github.com/uniwire-dev/uniwire/blob/main/examples/41_bess_container_dc_microgrid.uniwire.json) | en | TN-S | 3P+N | 1 |
| 42 | [Commune exemple : armoire d'éclairage public avec horloge astronomique](https://github.com/uniwire-dev/uniwire/blob/main/examples/42_public_lighting_cabinet_fr.uniwire.json) | fr | TT | 3P+N | 1 |
| 43 | [Small building services board: Siemens LOGO! 8 control of lighting and pumps](https://github.com/uniwire-dev/uniwire/blob/main/examples/43_logo_lighting_pumps.uniwire.json) | en | TN-S | 3P+N | 1 |
| 44 | [Packaging line control panel CP-100: Modicon M241 with EtherNet/IP remote I/O](https://github.com/uniwire-dev/uniwire/blob/main/examples/44_m241_remote_io_480v.uniwire.json) | en | TN-S | 3P | 1 |
| 45 | [Exploitation agricole exemple : armoire de pompage d'irrigation à variateur](https://github.com/uniwire-dev/uniwire/blob/main/examples/45_irrigation_vfd_plc_fr.uniwire.json) | fr | TT | 3P+N | 1 |
| 46 | [Office building (3 floors): passenger lift supply](https://github.com/uniwire-dev/uniwire/blob/main/examples/46_lift_machine_room.uniwire.json) | en | TN-S | 3P+N | 1 |
| 47 | [Example marina: shore power distribution to pontoon pedestals](https://github.com/uniwire-dev/uniwire/blob/main/examples/47_marina_shore_power.uniwire.json) | en | TN-S | 3P+N | 3 |
| 48 | [Immeuble de bureaux exemple : chaufferie pompe à chaleur (TD-CVC)](https://github.com/uniwire-dev/uniwire/blob/main/examples/48_heat_pump_plant_room_fr.uniwire.json) | fr | TN-S | 3P+N | 1 |
| 49 | [Example leisure centre: 50 kWe CHP running in parallel with the grid](https://github.com/uniwire-dev/uniwire/blob/main/examples/49_chp_parallel_grid.uniwire.json) | en | TN-S | 3P+N | 1 |
| 50 | [Example telecom shelter: -48 V DC power plant with battery backup and genset inlet](https://github.com/uniwire-dev/uniwire/blob/main/examples/50_telecom_shelter_48vdc.uniwire.json) | en | TT | 3P+N | 1 |
| 51 | [Station de pompage : TD process avec automate WAGO PFC200](https://github.com/uniwire-dev/uniwire/blob/main/examples/51_pumping_station_plc_fr.uniwire.json) | fr | TN-S | 3P+N | 1 |
| 52 | [Example workshop: dual supply, feeders selectable by removable links](https://github.com/uniwire-dev/uniwire/blob/main/examples/52_dual_source_selectable_feeders.uniwire.json) | en | TN-S | 3P+N | 1 |
| 53 | [Example office: hybrid inverter with rooftop PV, battery and essential loads board](https://github.com/uniwire-dev/uniwire/blob/main/examples/53_office_hybrid_inverter_pv_battery.uniwire.json) | en | TN-S | 3P+N | 1 |

To render an example yourself:

```bash
uniwire render examples/<name>.uniwire.json -f pdf -o out/<name>.pdf
uniwire bom examples/<name>.uniwire.json
```
