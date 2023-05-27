# Klipper plugin for tracking Filaments preset assigned to an Extruder
#
# Copyright (C) 2022-2023  Gareth Farrington <gareth@waves.ky>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging
import copy
import ast
import types

class FilamentPresets:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.save_vars = self.printer.lookup_object('save_variables')
        self.gcode = self.printer.lookup_object('gcode')

        # gcode macros in config:
        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self._on_set_filament_macro = gcode_macro.load_template(config,
                                'on_set_filament_gcode')
        self._on_clear_filament_macro = gcode_macro.load_template(config,
                                'on_clear_filament_gcode')
        # read presets from save_vars
        self._extruder_names = self._get_extruder_names()
        self._presets = self._load_filaments()
        self._assignments = self._build_assignment_map()
        self._register_filament_commands(self.gcode)
        for name in self._extruder_names:
            self._register_extruder_commands(self.gcode, name)
        # Register commands
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)

    # constants
    name_key = 'name'
    bed_key = 'bed'
    extruder_key = 'extruder'
    assigned_to_key = '_assigned_to'
    protected_keys = [name_key, bed_key, extruder_key, assigned_to_key]
    preset_defaults = {
        bed_key: .0, extruder_key: .0, assigned_to_key: []
    }

    def _register_filament_commands(self, gcode):
                # Filament preset manipulation command
        gcode.register_command('SETUP_FILAMENT', self.cmd_SETUP_FILAMENT,
                               desc=self.cmd_SETUP_FILAMENT_help)
        gcode.register_command('DELETE_FILAMENT', self.cmd_DELETE_FILAMENT,
                               desc=self.cmd_DELETE_FILAMENT_help)
        gcode.register_command('QUERY_FILAMENTS', self.cmd_QUERY_FILAMENTS,
                               desc=self.cmd_QUERY_FILAMENTS_help)

    def _register_extruder_commands(self, gcode, extruder):
        if extruder == 'extruder':
            self.gcode.respond_info("DEBUG: registering extruder", log=True)
            gcode.register_mux_command('SET_FILAMENT', 'EXTRUDER', None,
                        self.cmd_SET_FILAMENT, desc=self.cmd_SET_FILAMENT_help)
            gcode.register_mux_command('CLEAR_FILAMENT', 'EXTRUDER', None,
                        self.cmd_CLEAR_FILAMENT,
                        desc=self.cmd_CLEAR_FILAMENT_help)
            gcode.register_mux_command('PREHEAT', 'EXTRUDER', None,
                        self.cmd_PREHEAT, desc=self.cmd_PREHEAT_help)
            gcode.register_mux_command('PREHEAT_EXTRUDER', 'EXTRUDER', None,
                        self.cmd_PREHEAT_EXTRUDER,
                        desc=self.cmd_PREHEAT_EXTRUDER_help)
            gcode.register_mux_command('PREHEAT_BED', 'EXTRUDER', None,
                        self.cmd_PREHEAT_BED, desc=self.cmd_PREHEAT_BED_help)
            gcode.register_mux_command('HEAT_AND_WAIT', 'EXTRUDER', None,
                        self.cmd_HEAT_AND_WAIT,
                        desc=self.cmd_HEAT_AND_WAIT_help)
            gcode.register_mux_command('HEAT_EXTRUDER_AND_WAIT', 'EXTRUDER',
                        None, self.cmd_HEAT_EXTRUDER_AND_WAIT,
                        desc=self.cmd_HEAT_EXTRUDER_AND_WAIT_help)
            gcode.register_mux_command('HEAT_BED_AND_WAIT', 'EXTRUDER', None,
                        self.cmd_HEAT_BED_AND_WAIT,
                        desc=self.cmd_HEAT_BED_AND_WAIT_help)

        self.gcode.respond_info("DEBUG: registering extruder#: %s" % (extruder), log=True)
        gcode.register_mux_command('SET_FILAMENT', 'EXTRUDER', extruder,
                        self.cmd_SET_FILAMENT, desc=self.cmd_SET_FILAMENT_help)
        gcode.register_mux_command('CLEAR_FILAMENT', 'EXTRUDER', extruder,
                        self.cmd_CLEAR_FILAMENT,
                        desc=self.cmd_CLEAR_FILAMENT_help)
        gcode.register_mux_command('PREHEAT', 'EXTRUDER', extruder,
                        self.cmd_PREHEAT, desc=self.cmd_PREHEAT_help)
        gcode.register_mux_command('PREHEAT_EXTRUDER', 'EXTRUDER', extruder,
                        self.cmd_PREHEAT_EXTRUDER,
                        desc=self.cmd_PREHEAT_EXTRUDER_help)
        gcode.register_mux_command('PREHEAT_BED', 'EXTRUDER', extruder,
                        self.cmd_PREHEAT_BED, desc=self.cmd_PREHEAT_BED_help)
        gcode.register_mux_command('HEAT_AND_WAIT', 'EXTRUDER', extruder,
                        self.cmd_HEAT_AND_WAIT,
                        desc=self.cmd_HEAT_AND_WAIT_help)
        gcode.register_mux_command('HEAT_EXTRUDER_AND_WAIT', 'EXTRUDER',
                        extruder, self.cmd_HEAT_EXTRUDER_AND_WAIT,
                        desc=self.cmd_HEAT_EXTRUDER_AND_WAIT_help)
        gcode.register_mux_command('HEAT_BED_AND_WAIT', 'EXTRUDER', extruder,
                        self.cmd_HEAT_BED_AND_WAIT,
                        desc=self.cmd_HEAT_BED_AND_WAIT_help)

    # wrap the get_status call on the extruder so it includes the filament
    def _wrap_extruder_status(self, extruder_name):
        filaments = self
        extruder = self.printer.lookup_object(extruder_name)
        wrapped_get_status = extruder.get_status
        def get_status_wrapper(self, eventtime):
            sts = wrapped_get_status(eventtime)
            sts['filament'] = filaments._assignments[extruder_name]
            return sts
        extruder.get_status = types.MethodType(get_status_wrapper, extruder)

    def _handle_connect(self):
        for name in self._extruder_names:
            self._wrap_extruder_status(name)

    # build an empty set of filament assignments for all extruders
    def _get_extruder_names(self):
        extruders = []
        # allocate extruder slots from config
        for i in range(99):
            extruderName = 'extruder'
            if i:
                extruderName = 'extruder%d' % (i,)
            if not self.config.has_section(extruderName):
                break
            extruders.append(extruderName)
        return extruders

    def _call_macro(self, macro, macro_params):
        context = macro.create_template_context()
        context['params'] = macro_params
        macro.run_gcode_from_command(context)

    # copy actual assignment data from presets
    def _build_assignment_map(self):
        assignments = {}
        for name in self._extruder_names:
            assignments[name] = None

        # go through _presets and find ones that are assigned to an extruder
        for preset in self._presets:
            for extruder in preset[self.assigned_to_key]:
                # copy the preset and delete the extruders key
                preset_copy = copy.deepcopy(preset)
                preset_copy.pop(self.assigned_to_key, None)
                assignments[extruder] = preset_copy
        # update internal state
        return assignments

    def _load_filaments(self):
        # save_variables doesn't use this, but the param is required...
        event_time = self.reactor.monotonic()
        svv = self.save_vars.get_status(event_time)['variables']
        presets = list()
        # tread carefully because data can be tampered by user
        if not 'filaments' in svv:
            logging.info("No filaments found in [save_variables]")
            return presets
        # TODO: as much or as little validation as desired...
        # save_variables can be edited by hand, I dont want to delete someones
        # work because I cant parse it. Prefer failing on unexpected value:
        presets = svv['filaments']
        if not presets or not isinstance(presets, list):
            raise ValueError("'filaments' is not an array")
        names = {}
        for preset in presets:
            # fail on items that dont look like a preset
            if not isinstance(preset, dict) or (not preset[self.name_key]):
                raise ValueError("Item '%s' is not a valid Filament Preset"
                                        % (str(preset),))
            name = preset[self.name_key]
            # presets must have a name thats a string at least 2 chars long
            if not isinstance(name, str):
                raise ValueError("Filament name '%s' is not a string"
                                             % (str(name),))
            if len(name.strip()) < 2:
                raise ValueError("Filament name '%s' is too short"
                                             % (name,))
            # fail on duplicate names
            lower_name = name.strip().lower()
            if lower_name in names:
                raise ValueError("Multiple filament presets with the name '%s'"
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
        # when internal state changes, update the presets map
        self._assignments = self._build_assignment_map()

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
            except (ValueError, SyntaxError):
                raise gcmd.error("Unable to parse '%s' as a Python literal"
                                     % (str(raw_value),))

    def get_status(self, eventtime):
        presets = copy.deepcopy(self._presets)
        for preset in presets:
            preset.pop(self.assigned_to_key, None)
        return {
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

    def str_preset(self, preset):
        if preset is None:
            return "None"
        return "%s - %.0f/%.0f" % (preset[self.name_key],
                    preset[self.extruder_key],
                    preset[self.bed_key])

    cmd_QUERY_FILAMENTS_help = "_FILAMENTS"
    def cmd_QUERY_FILAMENTS(self, gcmd):
        gcmd.respond_info("Current Filaments:")
        for extruder_name in self._extruder_names:
            preset_str = self.str_preset(self._assignments[extruder_name])
            gcmd.respond_info("%s: %s" % (extruder_name, preset_str))

        gcmd.respond_info("Filament Presets:")
        preset_str = list()
        for preset in self._presets:
            preset_str.append(self.str_preset(preset))
        if len(preset_str) > 0:
            gcmd.respond_info('\n'.join(preset_str))
        else:
            gcmd.respond_info('No filaments set up.')

    # Get the extruder name and index based on the 'T' param
    def _get_extruder_arg(self, gcmd):
        extruder = gcmd.get('EXTRUDER', default=None)
        if extruder is None:
            # use the active extruder
            toolhead = self.printer.lookup_object('toolhead')
            extruder = toolhead.get_extruder().name
        return extruder, self._extruder_names.index(extruder)

    # common variable unpacking and validation code for the heating functions
    def _heat_cmd_preamble(self, gcmd):
        extruder_name, tool_index = self._get_extruder_arg(gcmd)
        preset = self._assignments[extruder_name]
        if preset is None:
            if len(self._extruder_names):
                raise gcmd.error("No filament set on %s" % (extruder_name))
            else:
                raise gcmd.error("No filament set")
        return extruder_name, tool_index, preset

    cmd_SET_FILAMENT_help = "SET_FILAMENT"
    def cmd_SET_FILAMENT(self, gcmd):
        name = self._validate_name_param(gcmd)
        extruder_name, extruder_index = self._get_extruder_arg(gcmd)
        filament_preset = self._find_preset(name)
        if filament_preset is None:
            raise gcmd.error("No filament preset named '%s' could be found"
                                         % (name))

        # wipe the extruder from the presets
        last_preset = self._remove_extruder(self._presets, extruder_name)
        last_preset_copy = None
        if not last_preset is None:
            last_preset_copy = copy.deepcopy(last_preset)
            last_preset_copy.pop(self.assigned_to_key, None)

        # add the extruder to the list of extruders on the selected preset
        filament_preset[self.assigned_to_key].append(extruder_name)
        preset_copy = copy.deepcopy(filament_preset)
        preset_copy.pop(self.assigned_to_key, None)
        self._save_presets()
        gcmd.respond_info("%s -> %s" % (extruder_name,
                                self.str_preset(preset_copy)))
        self._call_macro(self._on_set_filament_macro, {
            'EXTRUDER': extruder_name,
            'T': extruder_index,
            'PRESET': preset_copy,
            'LAST_PRESET': last_preset_copy
        })

    cmd_CLEAR_FILAMENT_help = "Clear the filament assigned to the extruder"
    def cmd_CLEAR_FILAMENT(self, gcmd):
        extruder_name, extruder_index = self._get_extruder_arg(gcmd)
        last_preset = self._remove_extruder(self._presets, extruder_name)
        last_preset_copy = None
        if not last_preset is None:
            last_preset_copy = copy.deepcopy(last_preset)
            last_preset_copy.pop(self.assigned_to_key, None)
        self._save_presets()
        gcmd.respond_info("%s -> None" % (extruder_name))
        self._call_macro(self._on_clear_filament_macro, {
            'EXTRUDER': extruder_name,
            'T': extruder_index,
            'LAST_PRESET': last_preset_copy
        })

    cmd_PREHEAT_help = "Start heating the extruder and bed"
    def cmd_PREHEAT(self, gcmd):
        self.cmd_PREHEAT_BED(gcmd)
        self.cmd_PREHEAT_EXTRUDER(gcmd)

    cmd_PREHEAT_EXTRUDER_help = "Start heating the extruder"
    def cmd_PREHEAT_EXTRUDER(self, gcmd):
        extruder, tool_index, preset = self._heat_cmd_preamble(gcmd)
        gcmd_M104 = self.gcode.create_gcode_command("M104", "M104", {
                            'S': preset[self.extruder_key],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M104(gcmd_M104)

    cmd_PREHEAT_BED_help = "Start heating the bed"
    def cmd_PREHEAT_BED(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_M140 = self.gcode.create_gcode_command("M140", "M140", {
                            'S': preset[self.bed_key],
                        })
        heater_bed = self.printer.lookup_object("heater_bed")
        heater_bed.cmd_M140(gcmd_M140)

    cmd_HEAT_AND_WAIT_help = '''Start heating the extruder and the bed, wait
                            for both to reach temperature'''
    def cmd_HEAT_AND_WAIT(self, gcmd):
        # start both heaters immediately
        self.cmd_PREHEAT(gcmd)
        # wait on the bed first because it takes the longest
        self.cmd_HEAT_BED_AND_WAIT(gcmd)
        self.cmd_HEAT_EXTRUDER_AND_WAIT(gcmd)

    cmd_HEAT_EXTRUDER_AND_WAIT_help = '''Heat the extruder and wait for it to
                                    reach temperature'''
    def cmd_HEAT_EXTRUDER_AND_WAIT(self, gcmd):
        extruder, tool_index, preset = self._heat_cmd_preamble(gcmd)
        gcmd_M109 = self.gcode.create_gcode_command("M109", "M109", {
                            'S': preset[self.extruder_key],
                            'T': tool_index
                        })
        printer_extruder = self.printer.lookup_object(extruder)
        printer_extruder.cmd_M109(gcmd_M109)

    cmd_HEAT_BED_AND_WAIT_help = '''Heat the bed and wait for it to reach
                                    temperature'''
    def cmd_HEAT_BED_AND_WAIT(self, gcmd):
        _, _, preset = self._heat_cmd_preamble(gcmd)
        gcmd_M190 = self.gcode.create_gcode_command("M190", "M190", {
                            'S': preset[self.bed_key],
                        })
        heater_bed = self.printer.lookup_object("heater_bed")
        heater_bed.cmd_M190(gcmd_M190)

def load_config(config):
    return FilamentPresets(config)
