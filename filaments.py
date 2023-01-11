# Klipper plugin for tracking Filaments preset assigned to an Extruder
#
# Copyright (C) 2022-2023  Gareth Farrington <gareth@waves.ky>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import copy
import ast

class FilamentPresets:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.save_vars = self.printer.lookup_object('save_variables')
        self.gcode = self.printer.lookup_object('gcode')

        # gcode macros in config:
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self._on_set_macro = gcode_macro.load_template(config, 'on_set_gcode')
        self._on_unset_macro = gcode_macro.load_template(config,
                                                            'on_unset_gcode')
        # read presets from save_vars
        self._assignments = self._setup_assignments()
        self._presets = self._load_filaments()
        self._register_commands(self.gcode)

    def _call_macro(self, macro, macro_params):
        context = macro.create_template_context()
        context['params'] = macro_params
        macro.run_gcode_from_command(context)

    def _register_commands(self, gcode):
        # Filament preset manipulation command
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

    name_key = 'name'
    bed_key = 'bed'
    extruder_key = 'extruder'
    assigned_to_key = '_assigned_to'
    protected_keys = [name_key, bed_key, extruder_key, assigned_to_key]
    preset_defaults = {
        bed_key: .0, extruder_key: .0, assigned_to_key: []
    }

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
            for extruder in preset[self.assigned_to_key]:
                # copy the preset and delete the extruders key
                preset_copy = copy.deepcopy(preset)
                preset_copy.pop(self.assigned_to_key, None)
                assignments[extruder] = preset_copy
        return assignments

    def _load_filaments(self):
        # save_variables doesn't use this, but the param is required...
        event_time = self.reactor.monotonic()
        vars = self.save_vars.get_status(event_time)['variables']
        presets = list()
        # tread carefully because data can be tampered by user
        if not 'filaments' in vars:
            logging.info("No filaments found in [save_variables]")
            return presets
        # TODO: as much or as little validation as desired...
        # save_variables can be edited by hand, I dont want to delete someones
        # work because I cant parse it. Prefer failing on unexpected value:
        presets = vars['filaments']
        if not presets or not type(presets) is list:
            raise ValueError("'filaments' is not an array")
        names = {}
        for preset in presets:
            # fail on items that dont look like a preset
            if (not type(preset) is dict) or (not preset[self.name_key]):
                raise ValueError("Item '%s' is not a valid Filament Preset" 
                                        % (str(preset),))
            name = preset[self.name_key]
            # presets must have a name thats a string at least 2 chars long
            if not type(name) is str:
                raise ValueError("Filament name '%s' is not a string"
                                             % (str(name),))
            if len(name.strip()) < 2:
                raise ValueError("Filament name '%s' is too short"
                                             % (name,))
            # fail on duplicate names
            lower_name = name.strip().lower()
            if lower_name in names:
                raise ValueError("Multiple Filament Presets with the name '%s'"
                                             % (name,))
            names[lower_name] = True
            # name sure all required keys are attached
            for key, value in self.preset_defaults.items():
                if not key in preset:
                    preset[key] = value
        return presets
    
    # check that a preset name is valid
    def _validate_name_param(self, gcmd):
        name = gcmd.get('NAME', default=None)
        if not name or not type(name) is str or not name.strip():
            raise gcmd.error("No NAME provided, one is required")
        name = name.strip()
        if len(name) < 2:
            raise gcmd.error("NAME must be at least 2 characters")
        return name

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
        last_preset = None
        for preset in presets:
            if extruder in preset[self.assigned_to_key]:
                last_preset = preset
                preset[self.assigned_to_key].remove(extruder)
        return last_preset

    # find a preset by name and pop it from the list
    def _find_preset(self, name):
        lower_name = name.lower()
        for preset in self._presets:
            if not preset[self.name_key].lower() == lower_name:
                continue
            found_preset = preset
            return found_preset
    
    # common variable unpacking and validation code for the heating functions
    def _heat_cmd_preamble(self, gcmd):
        extruder, tool_index = self._get_extruder_arg(gcmd)
        assignments = self._build_assignment_map()
        preset = assignments[extruder]
        if preset is None:
            if len(self._assignments):
                raise gcmd.error("No filament set on %s" % (extruder))
            else:
                raise gcmd.error("No filament set")
        return extruder, tool_index, preset
    
    def _copy_extra_fields(self, gcmd, preset):
        raw_params = gcmd.get_command_parameters()
        for param_name, raw_value in raw_params.items():
            param_key = param_name.lower()
            if param_key in self.protected_keys:
                # protected keys are handled in the SET_FILAMENTS macro
                continue
            try:
                value = ast.literal_eval(raw_value)
                preset[param_key] = value
            except (ValueError, SyntaxError) as e:
                raise gcmd.error("Unable to parse '%s' as a Python literal"
                                     % (str(raw_value),))

    def get_status(self, eventtime):
        assignments = self._build_assignment_map()
        presets = copy.deepcopy(self._presets)
        for preset in presets:
            preset.pop(self.assigned_to_key, None)
        return {
            self.assigned_to_key: assignments,
            'presets': presets
        }

    cmd_SETUP_FILAMENT_help = "SETUP_FILAMENT"
    def cmd_SETUP_FILAMENT(self, gcmd):
        name = self._validate_name_param(gcmd)
        # find an existing preset with that name:
        preset = self._find_preset(name)
        # if this is a new preset, initialize defaults:
        if preset is None:
            preset = copy.deepcopy(self.preset_defaults)
            self._presets.append(preset)
        # always overwrite the name to allow for capitalization changes
        preset[self.name_key] = name
        # get temp params
        extruder = gcmd.get_float('EXTRUDER', default=None)
        if not extruder is None:
            preset[self.extruder_key] = extruder
        bed = gcmd.get_float('BED', default=None)
        if not bed is None:
            preset[self.bed_key] = bed
        # store any additional parameters
        self._copy_extra_fields(gcmd, preset)
        # save preset
        self._save_presets()
        gcmd.respond_info("%s - %.0f/%.0f" %
                (preset[self.name_key],
                 preset[self.extruder_key],
                 preset[self.bed_key]))

    cmd_DELETE_FILAMENT_help = "DELETE_FILAMENT"
    def cmd_DELETE_FILAMENT(self, gcmd):
        name = self._validate_name_param(gcmd)
        preset = self._find_preset(name)
        if preset is None:
            raise gcmd.error("No filament preset named '%s' could be found"
                                         % (name))
        else:
            self._presets.remove(preset)
        self._save_presets()
    
    cmd_LIST_FILAMENTS_help = "LIST_FILAMENTS"
    def cmd_LIST_FILAMENTS(self, gcmd):
        preset_str = list()
        for preset in self._presets:
            preset_str.append("%s - %.0f/%.0f" % 
                (preset[self.name_key],
                 preset[self.extruder_key],
                 preset[self.bed_key]))
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
                    (preset[self.name_key],
                    preset[self.extruder_key],
                    preset[self.bed_key]))
        else:
            for extruder, preset in assignments:
                if preset is None:
                    gcmd.respond_info("%s: -" % (extruder))
                gcmd.respond_info("%s: %s - %.0f/%.0f" %
                    (extruder, preset[self.name_key],
                 preset[self.extruder_key],
                 preset[self.bed_key]))
    
    cmd_SET_FILAMENT_help = "SET_FILAMENT"
    def cmd_SET_FILAMENT(self, gcmd):
        name = self._validate_name_param(gcmd)
        extruder, extruder_index = self._get_extruder_arg(gcmd)
        filament_preset = self._find_preset(name)
        if filament_preset is None:
            raise gcmd.error("No filament preset named '%s' could be found"
                                         % (name))
        
        # wipe the extruder from the presets
        last_preset = self._remove_extruder(self._presets, extruder)
        last_preset_copy = None
        if not last_preset is None:
            last_preset_copy = copy.deepcopy(last_preset)
            last_preset_copy.pop(self.assigned_to_key, None)

        # add the extruder to the list of extruders on the selected preset
        filament_preset[self.assigned_to_key].append(extruder)
        preset_copy = copy.deepcopy(filament_preset)
        preset_copy.pop(self.assigned_to_key, None)
        self._save_presets()
        self._call_macro(self._on_set_macro, {
            'EXTRUDER': extruder,
            'T': extruder_index,
            'PRESET': preset_copy,
            'LAST_PRESET': last_preset_copy
        })
    
    cmd_UNSET_FILAMENT_help = "UNSET_FILAMENT"
    def cmd_UNSET_FILAMENT(self, gcmd):
        extruder, extruder_index = self._get_extruder_arg(gcmd)
        last_preset = self._remove_extruder(self._presets, extruder)
        last_preset_copy = None
        if not last_preset is None:
            last_preset_copy = copy.deepcopy(last_preset)
            last_preset_copy.pop(self.assigned_to_key, None)
        self._save_presets()
        self._call_macro(self._on_unset_macro, {
            'EXTRUDER': extruder,
            'T': extruder_index,
            'LAST_PRESET': last_preset_copy
        })

    cmd_PREHEAT_help = "PREHEAT"
    def cmd_PREHEAT(self, gcmd):
        self.cmd_PREHEAT_BED(gcmd)
        self.cmd_PREHEAT_EXTRUDER(gcmd)

    cmd_PREHEAT_EXTRUDER_help = "PREHEAT_EXTRUDER"
    def cmd_PREHEAT_EXTRUDER(self, gcmd):
        extruder, tool_index, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M104", "M104", { 
                            'S': preset[self.extruder_key],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M104(gcmd_save)

    cmd_PREHEAT_BED_help = "PREHEAT_BED"
    def cmd_PREHEAT_BED(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M140", "M140", { 
                            'S': preset[self.bed_key],
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
                            'S': preset[self.extruder_key],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M109(gcmd_save)
    
    cmd_HEAT_BED_AND_WAIT_help = "HEAT_BED_AND_WAIT"
    def cmd_HEAT_BED_AND_WAIT(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_save = self.gcode.create_gcode_command("M190", "M190", { 
                            'S': preset[self.bed_key],
                        })
        heater_bed = self.printer.lookup_object("heater_bed")
        heater_bed.cmd_M190(gcmd_save)

def load_config(config):
    return FilamentPresets(config)