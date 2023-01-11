# ⚠️⚠️⚠️ WARNING ⚠️⚠️⚠️
Status: Alpha
This is new code and is not heavily tested. In particular I haven't tested the multi-tool code paths.
Please file bugs on github.

If you are interested in more general discussion join this thread: https://klipper.discourse.group/t/assigning-a-filament-aka-thermal-preset-to-an-extruder/5849

----

# Filaments - Filament Presets for Klipper

----

# Config Reference

## [filaments]

Filament Presets. Associate a filament preset with each extruder, manage presets and preset driven heating tasks.

```
[filaments]
#on_set_gcode:
#   A list of G-Code commands to execute after the SET_FILAMENT macro runs. See
#   docs/Command_Templates.md for G-Code format. These parameters are pass to the gcode:
#   * 'EXTRUDER' - the name of the extruder. 'extruder', 'extruder1' etc.
#   * 'T' - the integer index of the extruder
#   * 'PRESET' - the filament preset that was just assigned t th extruder
#   * 'LAST_PRESET' - the filament preset that was previously assigned to the extruder, if any
#on_unset_gcode:
#   A list of G-Code commands to execute after the UNSET_FILAMENT macro runs. See
#   docs/Command_Templates.md for G-Code format. These parameters are pass to the gcode:
#   * 'EXTRUDER' - the name of the extruder. 'extruder', 'extruder1' etc.
#   * 'T' - the integer index of the extruder
#   * 'LAST_PRESET' - the filament preset that was previously assigned to the extruder, if any
```

----

# G-Code Commands
These commands handle basic tasks for filament presets

### [filament]
The following commands are available when a [filaments config section](#filaments) is enabled.

#### SETUP_FILAMENT
`SETUP_FILAMENT [NAME=<value>] [EXTRUDER=<bed_temp>] [BED=<bed_temp>]`: Create
or update a filament preset. The NAME argument is required and must be at least
2 characters long. EXTRUDER and BED are floating point numbers. You can pass any
number of additional parameters and these will be stored in the filament preset.
 The values of these parameters can be any valid Python literal. The names must 
be valid python dictionary keys. Dictionary keys will be stored in lower case.
Fields in the preset are overwritten if provided but otherwise preserved.

#### DELETE_FILAMENT
`DELETE_FILAMENT [NAME=<value>]` Delete a filament preset. The NAME argument is
required.

#### SET_FILAMENT
`SET_FILAMENT [NAME=<value>] [T=<index>]`: Associate the filament preset with
the extruder. The NAME parameter is required. The T parameter is the index 
of the extruder and is only required for multi-tool printers.

#### UNSET_FILAMENT
`UNSET_FILAMENT [T=<index>]`: Disassociate the extruder from the current 
filament preset, if any. The T parameter is the index of the extruder and is
only required for multi-tool printers.

#### SHOW_FILAMENT
`SHOW_FILAMENT`: Prints the currently associated filament preset to the
console. If the printer is multi-tool it prints an entry for every extruder.

#### LIST_FILAMENTS
`LIST_FILAMENTS`: Prints all filament presets to the console in the order they
were created.

#### PREHEAT_EXTRUDER
`PREHEAT_EXTRUDER T<index>` Heat the extruder to the configured extruder
temperature in the current filament preset. Will throw an error if no filament
preset is assigned. The T parameter is the index of the extruder and is
only required for multi-tool printers.

#### PREHEAT_BED
`PREHEAT_BED T<index>` Heat the heater bed to the configured bed
temperature in the current filament preset. Will throw an error if no filament
preset is assigned. The T parameter is the index of the extruder and is
only required for multi-tool printers.

#### PREHEAT
`PREHEAT T<index>` perform preheat for both extruder and bed. Will throw an 
error if no filament preset is assigned. The T parameter is the index of the
extruder and is only required for multi-tool printers.

#### HEAT_EXTRUDER_AND_WAIT
`HEAT_EXTRUDER_AND_WAIT T<index>` Heat the extruder to the configured extruder
temperature in the current filament preset and wait for that temperature
to be reached. Will throw an error if no filament preset is assigned. The T 
parameter is the index of the extruder and is only required for multi-tool
printers.

#### HEAT_BED_AND_WAIT
`HEAT_BED_AND_WAIT T<index>` Heat the heater bed to the configured bed
temperature in the current filament preset and wait for that temperature
to be reached. Will throw an error if no filament preset is assigned. The T 
parameter is the index of the extruder and is only required for multi-tool
printers.

#### HEAT_AND_WAIT
`HEAT_AND_WAIT T<index>` perform heat and wait for both extruder and bed. Will
throw an error if no filament preset is assigned.  The T parameter is the index
of the extruder and is only required for multi-tool printers.

----

# Status Reference

## filaments
The following information is available in the `filaments` object:
- `extruders`: A dictionary of the extruders in the printer. The key is the 
  extruder name. If no filament is assigned to the extruder the value will be
  `None`. If a filament is assigned the value is a filament preset dictionary 
  containing the following keys:
  - `name`: The name of the filament preset.
  - `extruder`: The temperature of the extruder.
  - `bed`: The temperature of the extruder.
  - custom keys: If custom keys were provided to SETUP_FILAMENT these will also
  be included.
- `profiles`: This is a list of all filament presets. Each entry is a filament 
  preset dictionary containing the following keys:
  - `name`: The name of the filament preset.
  - `extruder`: The temperature of the extruder.
  - `bed`: The temperature of the extruder.
  - custom keys: If custom keys were provided to SETUP_FILAMENT these will also
  be included.

# Use Cases

## General Usage Notes
Typically you set up filaments and then assign them to the extruder:

```
SETUP_FILAMENT NAME=PLA EXTRUDER=220 BED=65
SETUP_FILAMENT NAME=PETG EXTRUDER=220 BED=65

SET_FILAMENT NAME=PETG
```

Once set, filament presets and assignments are remembered across printer restarts. 
You can use this information in macros. Several macros are included to help 
with the most common heating tasks. These macros contain checks to make sure 
a filament preset is set and will abort any containing macro if it is not.

The order in which filaments are created with `SETUP_FILAMENT` is preserved. 
This might be a good ordering to display filament in a front end as it could
represent a user's preferred ordering.

Filament names are case preserving but case insensitive. `pla` and `PLA` refer
 to the same preset but will be displayed as written. Whenever you run 
`SETUP_FILAMENT` the case you set in the `NAME` parameter is saved.

## Filament Loading & Unloading
A common printer task is loading and unloading filament. With an assigned 
filament you can add a `HEAT_EXTRUDER_AND_WAIT` command to your macros to get 
the extruder up to temp before moving the extruder. e.g. using the sample macro
from [Klipper Screen](https://klipperscreen.readthedocs.io/en/latest/macros/#load_filament-unload_filament)
we only have to add 1 line:

```
[gcode_macro LOAD_FILAMENT]
gcode:
    {% set speed = params.SPEED|default(300) %}
    {% set max_velocity = printer.configfile.settings['extruder'].max_extrude_only_velocity %}
    SAVE_GCODE_STATE NAME=load_state
    HEAT_EXTRUDER_AND_WAIT  # make sure extruder is up to temp
    M300 # beep
    G91
    G92 E0
    G1 E350 F{max_velocity} # fast-load
    G1 E25 F{speed} # purge
    M300
    M300
    RESTORE_GCODE_STATE NAME=load_state
```

### Front End Improvement Suggestions
Front ends that want to automate this process or implement a `CHANGE_FILAMENT`
procedure can use `printer.filaments.extruders.extruder` to check if a filament 
is assigned to the extruder and if not, display the filament preset list (from 
`printer.filaments.presets`) to allow the user to select a filament preset.

`UNSET_FILAMENT` can be used to break the association between the extruder and
the filament preset. Calls to `HEAT_*` will fail with an error. The preset 
value is `None` and the front end can prompt the user to select a filament 
before executing the load/unload filament operation.

## `PRINT_START` and Calibration Prints

Klipper strongly suggests that users create a `PRINT_START` macro that takes in
 the extruder and bed temperatures. This works well if a slicer is passing those 
parameters in to the print. But for calibration prints run from the machine
there is no slicer. This has led to each macro attempting to do its own 
internal `PRINT_START` e.g. [PA_CAL](https://github.com/ksanislo/klipper-pa_cal/blob/master/src/pa_cal.cfg). 
This has hampered efforts to share calibration print macros as they are very
unlikely to work with your printer without modification.

[filaments] can help here to make the `PRINT_START` macro work when there is a
filament set but no temperatures were provided by the slicer:

```
[gcode_macro PRINT_START]
gcode:
    {% set EXTRUDER_TEMP = params.EXTRUDER_TEMP|default(0)|float %}
    {% set BED_TEMP = params.BED_TEMP|default(0)|float %}

    {% if EXTRUDER_TEMP and BED_TEMP %}
        M104 S{EXTRUDER_TEMP}  # heat up the extruder
        M140 S{BED_TEMP}       # heat up the bed
    {% else %}
        PREHEAT   # start heating the exturder and bed based on filament preset
                  # will halt the print if no preset is set
    {% endif %}

    # do print start tasks, homing, bed mesh etc...

    # before we start printing, make sure the extruder and bed have reached temp:
    {% if EXTRUDER_TEMP and BED_TEMP %}
        M109 S{EXTRUDER_TEMP}  # heat up the extruder
        M190 S{BED_TEMP}       # heat up the bed
    {% else %}
        HEAT_AND_WAIT   # heat both and wait for both based on filament preset
    {% endif %}
```

Now you can call `PRINT_START` with no arguments and it will just work. Creating
 a calibration print is therefor less complex. Lets take PA_CAL as an example:

 ```
 PRINT_START
 PA_CAL
 PRINT_END
 ```

Put that gcode in a file in the [virtial_sdcard] folder and call it 
`pa-cal.gcode`.

`PA_CAL` needs extra parameters but we can pass them via variables on the 
`PA_CAL` macro object:

```
[gcode_macro START_PA_CAL]
description: Print a Pressure Advance test pattern
gcode:
    # configure pressure advance
    SET_GCODE_VARIABLE MACRO=PA_CAL VARIABLE=extrusion_factor VALUE={extrusion_factor}
    SET_GCODE_VARIABLE MACRO=PA_CAL VARIABLE=nozzle VALUE={nozzle}

    # run print job
    SDCARD_PRINT_FILE FILENAME="pa-cal.gcode"
```

Now the macro runs as a print rather than as a macro so it can be paused
or canceled. Most of the front ends will present a nice UI for entering these
additional parameters. We should expect a lot more re-usable calibration macros 
using this technique.

## Reacting to Filament Changes

All of the klipper front ends allow you to run custom gcode when a preset is
selected. But they don't pass any context information about the filament change
so this feature is of limited value. Instead of this gode per-preset approach, 
[filaments] supports 2 macros that are triggered when a filament is set or unset.
These macros get passed useful context information about the filament change
including the extruder, new filament preset and previous filament preset.

Here is an example of using these macros just to print out that information:

```
[filaments]
on_set_gcode: 
    {action_respond_info("Filament Set. extruder: %s, T=%i, preset: %s, last_preset: %s" % (params.EXTRUDER, params.T, params.PRESET | string, params.LAST_PRESET | string))}
on_unset_gcode:
    {action_respond_info("Filament Unset. extruder: %s, T=%i, last_preset: %s" % (params.EXTRUDER, params.T, params.LAST_PRESET | string))}
```

sample output:
```
$ SET_FILAMENT NAME=PETG
// Filament Set. extruder: extruder, T=0, preset: {'name': 'PETG', 'extruder': 280.0, 'bed': 90.0}, last_preset: None
$ SET_FILAMENT NAME=PLA
// Filament Set. extruder: extruder, T=0, preset: {'name': 'PLA', 'extruder': 215.5, 'bed': 45.0}, last_preset: {'name': 'PETG', 'extruder': 280.0, 'bed': 90.0}
$ UNSET_FILAMENT
// Filament Unset. extruder: extruder, T=0, last_preset: {'name': 'PLA', 'extruder': 215.5, 'bed': 45.0}
```

I'm not super familiar with what people are using these gcode blocks for but
hopefully this is more useful and maintainable. this also has the benefit of
working across all front ends hooked up to klipper without having to copy your
gcode to multiple places.