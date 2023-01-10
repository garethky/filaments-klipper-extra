# Klipper plugin for tracking Filaments assigned to an Extruder
#
# Copyright (C) 2021-2022  Gareth Farrington <gareth@waves.ky>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import copy

# Filaments uses [save_variables] for storage, this means all changes can be saved without a printer restart
#
#
# Filaments exposes a printer object: `printer.filaments` which contains the following information:
#
# printer.filaments.presets - this is an array of the filament preset object:
# - name: the name of the filament
# - extruder: the temperature of the extruder
# - bed: the temperature of the bed
#
# printer.filaments.assignments - this is a map of the extruder name "extruder", "extruder1" etc to the filament name
# 
# The filament assigned to the extruder can be looked up as:
# printer.filaments.presets[printer.filaments.assignments.extruder]
#
# In save_variables the presets are stored as an array under the key 'filaments'
# Each preset has the name, extruder and bed keys and an extruders element that keeps a list of extruders that are currently assigned that filament.

# References:
# * [save_variables]: https://github.com/Klipper3d/klipper/blob/master/klippy/extras/save_variables.py

class FilamentsPrinterObject:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.save_vars = self.printer.lookup_object('save_variables')
        self.gcode = self.printer.lookup_object('gcode')
        # read presets from save_vars
        self._assignments = self._setup_assignments()
        self._presets = self._load_filaments()
        self._register_commands(self.gcode)

    def _register_commands(self, gcode):
        # Filament manipulation command
        gcode.register_command('SETUP_FILAMENT', self.cmd_SETUP_FILAMENT,
                               desc=self.cmd_SETUP_FILAMENT_help)
        gcode.register_command('DELETE_FILAMENT', self.cmd_DELETE_FILAMENT,
                               desc=self.cmd_DELETE_FILAMENT_help)
        gcode.register_command('LIST_FILAMENTS', self.cmd_LIST_FILAMENTS,
                               desc=self.cmd_LIST_FILAMENTS_help)
        gcode.register_command('FILAMENT_STATUS', self.cmd_FILAMENT_STATUS,
                               desc=self.cmd_FILAMENT_STATUS_help)
        gcode.register_command('SET_FILAMENT', self.cmd_SET_FILAMENT,
                               desc=self.cmd_SET_FILAMENT_help)
        gcode.register_command('UNSET_FILAMENT', self.cmd_UNSET_FILAMENT,
                               desc=self.cmd_UNSET_FILAMENT_help)
        # Temperature commands
        gcode.register_command('PREHEAT', self.cmd_PREHEAT,
                               desc=self.cmd_PREHEAT_help)
        gcode.register_command('PREHEAT_EXTRUDER', self.cmd_PREHEAT_EXTRUDER,
                               desc=self.cmd_PREHEAT_EXTRUDER_help)
        gcode.register_command('PREHEAT_BED', self.cmd_PREHEAT_BED,
                               desc=self.cmd_PREHEAT_BED_help)
        gcode.register_command('HEAT_AND_WAIT', self.cmd_HEAT_AND_WAIT,
                               desc=self.cmd_HEAT_AND_WAIT_help)
        gcode.register_command('HEAT_EXTRUDER_AND_WAIT',
                               self.cmd_HEAT_EXTRUDER_AND_WAIT,
                               desc=self.cmd_HEAT_EXTRUDER_AND_WAIT_help)
        gcode.register_command('HEAT_BED_AND_WAIT', self.cmd_HEAT_BED_AND_WAIT,
                               desc=self.cmd_HEAT_BED_AND_WAIT_help)

    # build an empty set of filament assignments for all extruders
    def _setup_assignments(self):
        assignments = dict()
        # allocate extruder slots from config
        for i in range(99):
            extruderName = 'extruder'
            if i:
                extruderName = 'extruder%d' % (i,)
            if not self.config.has_section(extruderName):
                break
            assignments[extruderName] = None
        return assignments

    # copy actual assignment data from presets
    def _build_assignment_map(self):
        assignments = copy.deepcopy(self._assignments)

        # go through _presets and find ones that are assigned to an extruder
        for preset in self._presets:
            if not 'extruders' in preset or not len(preset['extruders']):
                continue
            for extruder in preset['extruders']:
                if extruder in assignments.keys():
                    # copy the preset and delete the extruders key
                    preset_copy = copy.deepcopy(preset)
                    preset_copy.pop('extruders', None)
                    assignments[extruder] = preset_copy
        return assignments

    def _load_filaments(self):
        # save_variables doesn't use this, but the param is required...
        eventtime = self.reactor.monotonic()
        vars = self.save_vars.get_status(eventtime)['variables']
        presets = list()
        # tread carefully because data can be tampered by user
        if not 'filaments' in vars:
            logging.info("No filaments found in [save_variables]")
            return presets
        
        # TODO: as much or as little validation as desired...
        #if not type(filaments) is list:
        #    return presets
        #for filament in filaments:
        #    if not (type(filament) is dict and 'name' in filament 
        #            and 'extruder' in filament and 'bed' in filament):
        #        continue
        #    preset = {
        #        'name': filament['name'],
        #        'extruder': 
        #    }
        return vars['filaments']
    
    # check that 
    def _validate_name(self, gcmd, name):
        if not name:
            raise gcmd.error("No NAME provided, one is required")
        if len(name) < 2:
            raise gcmd.error("NAME must be at least 2 characters")

    # output presets and assignment data to [save_variables]
    def _save_presets(self):
        gcmd_save = self.gcode.create_gcode_command("SAVE_VARIABLE",
                        "SAVE_VARIABLE", { 
                            'VARIABLE': 'filaments',
                            'VALUE': str(self._presets)
                        })
        self.save_vars.cmd_SAVE_VARIABLE(gcmd_save)

    # Get the extruder name and index based on the 'T' param
    def _get_extruder_arg(self, gcmd):
        extruder_index = gcmd.get('T', default=None)
        # check if extruder index is required and if the number is valid
        if not len(self._assignments):
            raise gcmd.error('This printer has no extruders')
        elif len(self._assignments) == 1:
            return 'extruder', 0
        else:
            if extruder_index is None:
                raise gcmd.error(
                    'Multi-tool printers require a tool argument e.g. T0')
            elif extruder_index == 0:
                return 'extruder', 0
            else:
                return 'extruder%d' % (extruder_index,), extruder_index
    
    # if the target extruder appears anywhere in the presets delete it
    def _remove_extruder(self, presets, extruder):
        for preset in presets:
            if 'extruders' in preset and extruder in preset['extruders']:
                preset['extruders'].remove(extruder)

    # find a preset by name and pop it from the list
    def _pop_preset(self, presets, name):
        lower_name = name.lower()
        for preset in presets:
            if not preset['name'].lower() == lower_name:
                continue
            found_preset = preset
            self._presets.remove(preset)
            return found_preset
    
    # common variable unpacking and validation code for the heating functions
    def _heat_cmd_preamble(self, gcmd):
        extruder, tool_index = self._get_extruder_arg(gcmd)
        assignments = self._build_assignment_map()
        preset = assignments[extruder]
        if preset is None:
            # TODO: nicer error messages for mono-tool printers
            raise gcmd.error("No filament set on %s" % (extruder))
        return extruder, tool_index, preset

    def get_status(self, eventtime):
        filaments = self._build_assignment_map()
        presets = copy.deepcopy(self._presets)
        for preset in presets:
            preset.pop('extruders', None)
        filaments['presets'] = presets
        return filaments

    cmd_SETUP_FILAMENT_help = "SETUP_FILAMENT"
    def cmd_SETUP_FILAMENT(self, gcmd):
        name = gcmd.get('NAME', default=None)
        self._validate_name(gcmd, name)
        
        extruder = gcmd.get_float('EXTRUDER', default=.0)
        bed = gcmd.get_float('BED', default=.0)
        filament = {'name': name, 'extruder': extruder,
                    'bed': bed, 'extruders': []}
        # find an existing filament and replace it instead:
        replaced_preset = self._pop_preset(self._presets, name)
        #TODO: if the user doesn't pass temps dont clobber them, copy them from replaced_preset
        if replaced_preset is not None and 'extruders' in replaced_preset:
            filament['extruders'] = replaced_preset['extruders']
        self._presets.append(filament)
        self._save_presets()
        gcmd.respond_info("%s - %.0f/%.0f" %
                (filament['name'], filament['extruder'], filament['bed']))

    cmd_DELETE_FILAMENT_help = "DELETE_FILAMENT"
    def cmd_DELETE_FILAMENT(self, gcmd):
        name = gcmd.get('NAME', default=None)
        self._validate_name(gcmd, name)
        self._pop_preset(self._presets, name)
        self._save_presets()
    
    cmd_LIST_FILAMENTS_help = "LIST_FILAMENTS"
    def cmd_LIST_FILAMENTS(self, gcmd):
        preset_str = list()
        for preset in self._presets:
            preset_str.append("%s - %.0f/%.0f" % 
                (preset['name'], preset['extruder'], preset['bed']))
        if len(preset_str) > 0:
            gcmd.respond_info('\n'.join(preset_str))
        else:
            gcmd.respond_info('No filaments set up.')
    
    cmd_FILAMENT_STATUS_help = "FILAMENT_STATUS"
    def cmd_FILAMENT_STATUS(self, gcmd):
        assignments = self._build_assignment_map()
        if len(self._assignments) == 1:
            if assignments['extruder'] is None:
                gcmd.respond_info("No Filament Set")
            else:
                preset = assignments['extruder']
                gcmd.respond_info("%s - %.0f/%.0f" %
                    (preset['name'], preset['extruder'], preset['bed']))
        else:
            for extruder, preset in assignments:
                if preset is None:
                    gcmd.respond_info("%s: -" % (extruder))
                gcmd.respond_info("%s: %s - %.0f/%.0f" %
                    (extruder, preset['name'], preset['extruder'],
                     preset['bed']))
    
    cmd_SET_FILAMENT_help = "SET_FILAMENT"
    def cmd_SET_FILAMENT(self, gcmd):
        name = gcmd.get('NAME', default=None)
        self._validate_name(gcmd, name)
        lower_name = name.lower()
        extruder, _ = self._get_extruder_arg(gcmd)

        # go through the list of presets and look for the one that matches:
        filament_preset = None
        for preset in self._presets:
            if preset['name'].lower() == lower_name:
                filament_preset = preset
                break
        
        if filament_preset is None:
            raise gcmd.error("No filament preset named '%s' could be found" % (name))
        
        # wipe the extruder from the presets
        self._remove_extruder(self._presets, extruder)

        # add the extruder to the list of extruders on the selected preset
        if not 'extruders' in filament_preset:
            filament_preset['extruders'] = list()
        filament_preset['extruders'].append(extruder)
        self._save_presets()
    
    cmd_UNSET_FILAMENT_help = "UNSET_FILAMENT"
    def cmd_UNSET_FILAMENT(self, gcmd):
        name = gcmd.get('NAME', default=None)
        self._validate_name(gcmd, name)
        extruder, _ = self._get_extruder_arg(gcmd)
        self._remove_extruder(self._presets, extruder)

    cmd_PREHEAT_help = "PREHEAT"
    def cmd_PREHEAT(self, gcmd):
        self.cmd_PREHEAT_BED(gcmd)
        self.cmd_PREHEAT_EXTRUDER(gcmd)

    cmd_PREHEAT_EXTRUDER_help = "PREHEAT_EXTRUDER"
    def cmd_PREHEAT_EXTRUDER(self, gcmd):
        extruder, tool_index, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M104", "M104", { 
                            'S': preset['extruder'],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M104(gcmd_save)

    cmd_PREHEAT_BED_help = "PREHEAT_BED"
    def cmd_PREHEAT_BED(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M140", "M140", { 
                            'S': preset['bed'],
                        })
        heater_bed = self.printer.lookup_object("heater_bed")
        heater_bed.cmd_M140(gcmd_save)
    
    cmd_HEAT_AND_WAIT_help = "HEAT_AND_WAIT"
    def cmd_HEAT_AND_WAIT(self, gcmd):
        # start both heaters immediately
        self.cmd_PREHEAT()
        # wait on the bed first because it takes the longest
        self.cmd_HEAT_BED_AND_WAIT(gcmd)
        self.cmd_HEAT_EXTRUDER_AND_WAIT(gcmd)
    
    cmd_HEAT_EXTRUDER_AND_WAIT_help = "HEAT_EXTRUDER_AND_WAIT"
    def cmd_HEAT_EXTRUDER_AND_WAIT(self, gcmd):
        extruder, tool_index, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M109", "M109", { 
                            'S': preset['extruder'],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M109(gcmd_save)
    
    cmd_HEAT_BED_AND_WAIT_help = "HEAT_BED_AND_WAIT"
    def cmd_HEAT_BED_AND_WAIT(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M190", "M190", { 
                            'S': preset['bed'],
                        })
        heater_bed = self.printer.lookup_object("heater_bed")
        heater_bed.cmd_M190(gcmd_save)

def load_config(config):
    return FilamentsPrinterObject(config)