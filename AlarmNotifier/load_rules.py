python3 <<'PYEOF'
import tango
RULES = [
 "name=leemWaterHv1 enabled=yes dev=leem/safety/interlockhv1 alarm=ALARM,FAULT ok=ON ctx=leem/safety/interlockhv1,leem/safety/interlockhv1/LastTripReason msg=Interlock del agua del doser 1 disparado",
 "name=leemWaterHv2 enabled=yes dev=leem/safety/interlockhv2 alarm=ALARM,FAULT ok=ON ctx=leem/safety/interlockhv2,leem/safety/interlockhv2/LastTripReason msg=Interlock del agua del doser 2 disparado",
 "name=leemP2Water enabled=yes dev=leem/safety/interlockP2lens alarm=ALARM,FAULT ok=ON ctx=leem/safety/interlockP2lens,leem/safety/interlockP2lens/LastTripReason msg=Interlock del agua de la lente P2 de LEEM",
 "name=leemColumnsIonPump enabled=yes dev=leem/vacuum/columnsionpump alarm=ALARM,FAULT,OFF ok=ON ctx=leem/vacuum/columnsionpump msg=Iónica columnas LEEM apagada",
 "name=leemTurboWater enabled=yes dev=leem/warn/turbowater alarm=ALARM,FAULT ok=ON when=leem/vacuum/turboPCH:ON,STANDBY ctx=leem/warn/turbowater,leem/warn/turbowater/LastTripReason msg=Interlock del agua del turbo del LEEM disparado",
 "name=leemTurboTemp enabled=yes dev=leem/warn/turbotemp alarm=ALARM,FAULT ok=ON when=leem/vacuum/turboPCH:ON,STANDBY ctx=leem/warn/turbotemp,leem/warn/turbotemp/LastTripReason msg=Temperatura del motor del turbo del LEEM alta",
 "name=mossCompresor enabled=yes dev=mossbauer/warn/watercompressor alarm=ALARM,FAULT ok=ON ctx=mossbauer/safety/waterflow/newcompressor msg=Agua del compresor del Mossbauer parada",
 "name=vsmMagnetWater enabled=yes dev=vsm/safety/interlockmagnetwater alarm=ALARM,FAULT ok=ON ctx=vsm/safety/interlockmagnetwater,vsm/safety/interlockmagnetwater/LastTripReason msg=Interlock del agua del imán del VSM",
 "name=xpsIonPump enabled=yes dev=xps/vacuum/ionpump alarm=ALARM,FAULT,OFF ok=ON ctx=xps/vacuum/ionpump msg=Iónica XPS apagada",
 "name=xpsWater enabled=yes dev=xps/safety/interlockxraygun alarm=ALARM,FAULT ok=ON ctx=xps/safety/water/xray,xps/safety/interlockxraygun/LastTripReason msg=Interlock del agua del XPS disparado",
]
db = tango.Database()
db.put_device_property("lab/alarm/notifier", {"Rules": RULES})
print(tango.DeviceProxy("lab/alarm/notifier").ReloadRules())
PYEOF
