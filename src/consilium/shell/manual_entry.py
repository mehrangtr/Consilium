"""A multiline local entry slot; EOF cancels and never accepts partial content."""

def collect_manual_text(candidate_id, *, read_line, write, max_bytes=262144):
    marker = 'END MANUAL ' + str(candidate_id)
    write('Paste the manual answer or critique here. Blank lines and spaces are preserved.')
    write('Finish with this exact line: ' + marker)
    write('End of input cancels without staging or accepting partial content.')
    lines = []
    size = 0
    while True:
        try:
            line = read_line()
        except (EOFError, StopIteration):
            return None
        if line is None:
            return None
        if type(line) is not str:
            raise ValueError('Manual input must be text')
        if line == marker:
            return '\n'.join(lines)
        size += len(line.encode('utf-8')) + (1 if lines else 0)
        if size > max_bytes:
            raise ValueError('Manual input exceeds local byte limit')
        lines.append(line)
