# AlarmNotifier

Vigila el `State` de otros device servers y avisa por correo. Sustituto
simplificado de PANIC/PyAlarm.

No evalúa umbrales numéricos: eso lo hacen instancias de `AnalogInterlock` en
modo watch-only, en la Pi del instrumento. Aquí solo se leen veredictos.

**No actúa.** Lo que deba interrumpir un experimento va en un interlock; lo que
no deba ocurrir nunca, en una cadena de hardware.

## Instalación en el repositorio

Colocar `AlarmNotifier/` en la raíz de `SURFMOSS_TangoDS` y añadir una línea a
cada una de las tres secciones de `pyproject.toml`. En las tres va justo
detrás de `AGPolaritySwitch`, que es quien lo precede alfabéticamente.

```toml
[project.scripts]
# AlarmNotifier
AlarmNotifier = "AlarmNotifier:main"
```

```toml
[tool.setuptools]
packages = [
    "AGPolaritySwitch",
    "AlarmNotifier",
    "AMLPGC1",
```

```toml
[tool.setuptools.package-dir]
AlarmNotifier        = "AlarmNotifier/AlarmNotifier"
```

Sin dependencias nuevas: solo biblioteca estándar y PyTango.

⚠️ Este servidor corre en **wolframite**, no en una Pi. No va en la raíz NFS
compartida: se instala en wolframite directamente.

```bash
cd /opt/tango/SURFMOSS_TangoDS      # en wolframite
sudo pip install --no-deps --break-system-packages -e .
which AlarmNotifier
```

## Registro

Servidor `AlarmNotifier/lab`, clase `AlarmNotifier`, device
`lab/alarm/notifier`, host wolframite.

wolframite ya tiene un `tango-starter` corriendo. Añadir este servidor a su
lista de control desde Astor, nivel de arranque 1.

## Requisito previo

`msmtp` configurado y funcionando en wolframite, con `/usr/sbin/sendmail`
disponible. Ver `notificaciones-gmail-linux.md`. Comprobar antes de nada:

```bash
echo -e "To: destino@ejemplo\nSubject: prueba\n\nhola" | /usr/sbin/sendmail -t
```

Si eso no llega, este servidor tampoco.

## Configuración mínima en Jive

| Propiedad | Valor |
|---|---|
| `Recipients` | `juan.delafiguera@iqf.csic.es` |
| `Rules` | una regla por línea (ver abajo) |
| `ReportSchedule` | `mon 08:00` |

⚠️ `Rules` y `Recipients` son **arrays de strings**. En Jive hay que meter cada
elemento en su línea. Es `dtype=('str',)` a propósito: con `'str'` PyTango se
queda solo con el primer elemento y perderías todas las reglas menos una.

## Formato de regla

Pares `clave=valor` separados por espacios. `msg=` va **al final**, porque se
lleva el resto de la línea. Líneas vacías y las que empiezan por `#` se ignoran.

```
name=xpsWater dev=xps/safety/waterinterlock alarm=ALARM,FAULT ok=ON ctx=xps/safety/water/xray msg=Interlock del agua del XPS disparado
```

| Campo | Oblig. | Def. | Significado |
|---|---|---|---|
| `name` | sí | — | Único. Es lo que se pasa a `Snooze` y `Acknowledge`. |
| `dev` | sí¹ | — | Device cuyo `State` se mira. |
| `attr` | sí¹ | — | `dominio/familia/miembro/atributo`, para `op=edge`. |
| `op` | no | `state` | `state` o `edge`. |
| `alarm` | no | `ALARM,FAULT` | Estados que disparan. |
| `ok` | no | `ON` | Estados que dan por recuperado. |
| `persist` | no | `2` | Sondeos consecutivos antes de disparar. |
| `enabled` | no | `yes` | `no` la deja inerte pero visible. |
| `onunknown` | no | `alarm` | `ignore` si el device se apaga a propósito. |
| `to` | no | — | **Sustituye** a `Recipients`. |
| `cc` | no | — | **Añade** a `Recipients`. |
| `ctx` | no | — | Atributos a leer y adjuntar al cuerpo. |
| `msg` | no | `name` | Texto del asunto. Va el último. |

¹ `dev` para `op=state`, `attr` para `op=edge`.

Un estado que no está ni en `alarm=` ni en `ok=` (`INIT`, `MOVING`) **mantiene**
la regla como estaba: ni dispara ni recupera. Eso es lo que evita que un `Init`
desde Jive genere correo.

Una regla mal escrita deja el device en `FAULT` con el nombre de la culpable en
el `Status`. Nunca se ignora en silencio.

## Comandos

| Comando | Argumento | Efecto |
|---|---|---|
| `Snooze` | `[nombre, horas]` | Duerme una regla. Rechaza más de `MaxSnoozeHours`. |
| `Wake` | `nombre` | La despierta antes de tiempo. |
| `Acknowledge` | `nombre` | Calla los recordatorios; la alarma sigue activa. |
| `AcknowledgeAll` | — | Para una mañana mala. |
| `Report` | — → `str` | La tabla de estado, para verla desde Jive. |
| `TestMail` | — | Manda el informe ahora. |
| `SendMessage` | `[asunto, cuerpo]` | Correo arbitrario. **No llamar desde el lazo de un DS de seguridad.** |
| `ReloadRules` | — → `str` | Relee `Rules` sin `Init`, conservando el estado de las reglas cuyo texto no ha cambiado. |

## Procedimiento de prueba

1. `TestMail` desde Jive. Debe llegar un correo con la tabla de reglas. Si no
   llega, mirar `LastMailError` y `sudo tail /var/log/msmtp.log`.
2. Con el interlock del XPS en `ON`, `Report` debe mostrar `xpsWater NORM`.
3. Comando `Trip` sobre `xps/safety/waterinterlock`. A los dos sondeos
   (`persist=2`, 20 s) debe llegar el correo de ALARMA, con el caudal en el
   bloque de contexto.
4. `Reset` sobre el interlock. Debe llegar el de RESUELTO.
5. Parar `AnalogInterlock/xps` desde Astor. A los 5 min
   (`UnknownCycles=30` × 10 s) debe llegar el de SIN LECTURA. **Éste es el que
   justifica el ejercicio**: es el fallo que un vigilante basado en umbrales no
   ve.
6. `Snooze ["xpsWater", "0.05"]` (3 min), repetir el paso 3 y comprobar que no
   llega nada. A los 3 min despierta sola.
7. Reiniciar el servidor con un snooze activo y comprobar que sigue dormida:
   el atributo `SnoozeState` es `memorized` y se recupera de la DB.

## Quién vigila al vigilante

Si este servidor muere, dejas de recibir correos y eso se parece mucho a que
todo va bien.

- `UpdateCount` se publica como latido, para que otro lo mire.
- El correo de `ReportSchedule` es lo que de verdad cierra el lazo: **si un
  lunes no llega nada, eso también es información.** Por eso conviene no dejar
  `ReportSchedule` vacío.

Un `AnalogInterlock` watch-only apuntando a este `UpdateCount` detecta la
congelación, pero no puede avisar: quien leería su `ALARM` es justamente el que
está muerto. Sirve para el sinóptico, no para el correo.
