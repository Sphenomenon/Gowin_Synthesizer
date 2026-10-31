"""Read Gowin source/routed netlist hierarchy and scalar/bit-select connectivity."""

import re


IDENTIFIER = r'(?:\\[^\s]+|[A-Za-z_$][A-Za-z0-9_$]*)'


class SynthesisNetlist:
    def __init__(self, text, top):
        self.modules, self.frames, self.cells, self.buffers, self.ranges = {}, {}, {}, {}, {}
        self.scopes, self.directions = {}, {}
        pattern = re.compile(r'^[ \t]*(' + IDENTIFIER + r')[ \t]+(' + IDENTIFIER + r')[ \t]*\((.*?)^[ \t]*\);',
                             re.M | re.S)
        for match in re.finditer(r'^module\s+(' + IDENTIFIER + r')\s*\((.*?)^endmodule\b', text, re.M | re.S):
            name = match[1].removeprefix('\\')
            if name in self.modules:
                raise ValueError('native duplicate netlist module: ' + name)
            parameters = {}
            for label, parameter, value in re.findall(r'defparam\s+(' + IDENTIFIER + r')\s*\.(\w+)\s*=\s*([^;]+);', match[2]):
                label = label.removeprefix('\\')
                if parameter in parameters.setdefault(label, {}):
                    raise ValueError('native duplicate netlist parameter: ' + label + '.' + parameter)
                parameters[label][parameter] = value.strip()
            instances = {}
            for instance in pattern.finditer(match[2]):
                kind, label = instance[1].removeprefix('\\'), instance[2].removeprefix('\\')
                if label in instances:
                    raise ValueError('native duplicate instance: ' + label)
                ports = {port.removeprefix('\\'): net.strip() for port, net in
                         re.findall(r'\.(' + IDENTIFIER + r')\s*\(\s*([^()]*?)\s*\)', instance[3])}
                instances[label] = dict(kind=kind, ports=ports, parameters=parameters.get(label, {}))
            self.modules[name] = instances
            self.directions[name] = {net.removeprefix('\\'): direction for direction, net in re.findall(
                r'^(input|output|inout)\s+(?:(?:wire|reg|logic)\s+)?(?:\[\d+:\d+\]\s+)?(' + IDENTIFIER + r')\s*;',
                match[2], re.M)}
            self.ranges[name] = {net.removeprefix('\\'): (int(left), int(right)) for left, right, net in
                                 re.findall(r'^(?:input|output|inout|wire)\s+\[(\d+):(\d+)\]\s+(' + IDENTIFIER + r')\s*;',
                                            match[2], re.M)}
            self.buffers[name] = {cell['ports']['O']: cell['ports']['I'] for cell in instances.values()
                                  if cell['kind'] in ('IBUF', 'BUFG') and {'O', 'I'}.issubset(cell['ports'])}
        if top not in self.modules:
            raise ValueError('native netlist top missing: ' + top)
        self.frames[''] = dict(kind=top, ports={})
        self._walk(top, '', ())

    def _walk(self, kind, prefix, ancestors):
        if kind in ancestors:
            raise ValueError('native recursive netlist hierarchy')
        for label, instance in self.modules[kind].items():
            instance_path = prefix + '/' + label if prefix else label
            if instance_path in self.cells:
                raise ValueError('native ambiguous flattened/hierarchical instance: ' + instance_path)
            self.cells[instance_path] = instance
            self.scopes[instance_path] = prefix
            if instance['kind'] in self.modules:
                self.frames[instance_path] = instance
                self._walk(instance['kind'], instance_path, (*ancestors, kind))

    def canonical(self, scope, net, seen=()):
        key = (scope, net)
        if key in seen:
            raise ValueError('native cyclic scalar net connection')
        if re.fullmatch(r"1'b[01]", net):
            return net
        frame = self.frames[scope]
        if scope and net in frame['ports']:
            return self.canonical(self.scopes[scope], frame['ports'][net], (*seen, key))
        selected = re.fullmatch(r'([A-Za-z_$][A-Za-z0-9_$]*)\[(\d+)\]', net)
        if scope and selected and selected[1] in frame['ports']:
            formal = self.ranges[frame['kind']].get(selected[1])
            if not formal or not min(formal) <= int(selected[2]) <= max(formal):
                raise ValueError('native invalid vector port bit: ' + net)
            offset = abs(int(selected[2]) - formal[1])
            width = abs(formal[0] - formal[1]) + 1
            binding = frame['ports'][selected[1]]
            parent = self.scopes[scope]
            part = re.fullmatch(r'([A-Za-z_$][A-Za-z0-9_$]*)\[(\d+)(?::(\d+))?\]', binding)
            if binding.startswith('{') and binding.endswith('}'):
                bits = self.concatenation_bits(parent, binding)
                if len(bits) != width:
                    raise ValueError('native unsupported vector port binding: ' + binding)
                target = bits[offset]
            elif part and part[3] is None and width == 1:
                target = binding
            else:
                actual = ((int(part[2]), int(part[3])) if part and part[3] is not None else
                          self.ranges[self.frames[parent]['kind']].get(binding))
                if actual and abs(actual[0] - actual[1]) + 1 == width:
                    index = actual[1] + offset * (1 if actual[0] >= actual[1] else -1)
                    target = (part[1] if part else binding) + '[' + str(index) + ']'
                elif width == 1 and re.fullmatch(IDENTIFIER, binding):
                    target = binding
                else:
                    raise ValueError('native unsupported vector port binding: ' + binding)
            return self.canonical(parent, target, (*seen, key))
        if net in self.buffers[frame['kind']]:
            return self.canonical(scope, self.buffers[frame['kind']][net], (*seen, key))
        return (scope + '/' if scope else '') + net

    def concatenation_bits(self, scope, binding):
        bits = []
        for member in reversed(binding[1:-1].split(',')):
            member = member.strip()
            selected = re.fullmatch(r'([A-Za-z_$][A-Za-z0-9_$]*)\[(\d+)(?::(\d+))?\]', member)
            literal = re.fullmatch(r"(\d+)'b([01]+)", member)
            if literal and int(literal[1]) == len(literal[2]):
                bits.extend("1'b" + bit for bit in reversed(literal[2]))
            elif selected and selected[3] is None:
                bits.append(member)
            else:
                actual = ((int(selected[2]), int(selected[3])) if selected and selected[3] is not None else
                          self.ranges[self.frames[scope]['kind']].get(member))
                if actual:
                    step = 1 if actual[0] >= actual[1] else -1
                    stem = selected[1] if selected else member
                    bits.extend(stem + '[' + str(index) + ']' for index in range(actual[1], actual[0] + step, step))
                elif re.fullmatch(IDENTIFIER, member):
                    bits.append(member)
                else:
                    raise ValueError('native unsupported vector port binding: ' + binding)
        return bits

    def pin(self, instance_path, port):
        return self.canonical(self.scopes[instance_path], self.cells[instance_path]['ports'][port])
