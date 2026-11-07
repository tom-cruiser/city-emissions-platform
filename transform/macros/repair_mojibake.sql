{#- Repair EDGAR's double-encoded names: UTF-8 bytes that were decoded as Windows-1252.
    e.g. 'SÃ£o Paulo' -> 'São Paulo', 'Ã‡orum' -> 'Çorum', 'Ã\u0081vila' -> 'Ávila'.

    How: map every character back to the single byte it was decoded from, then decode
    those bytes as UTF-8. translate() turns the 27 Windows-1252-specific characters
    (€, ‚, ‡, ‰, Œ, “, ™ ...) back into bytes 0x80-0x9F; the five bytes Windows-1252 leaves
    undefined (0x81, 0x8D, 0x8F, 0x90, 0x9D) already survive as control characters
    U+0081 etc. LATIN1 then maps U+0000-U+00FF one-to-one onto bytes.

    Applied to every non-ASCII value: in EDGAR v2024 all 608 distinct non-ASCII names and
    countries are double-encoded, and all 608 decode. A correctly encoded name such as
    'Bogotá' is not valid UTF-8 after this and makes the build FAIL. That is intended: it
    means a new EDGAR release fixed its encoding and this repair must be revisited.

    Characters already replaced by '?' upstream (e.g. 'Bia?ystok') cannot be recovered. -#}
{% macro repair_mojibake(expr) -%}
    {%- set cp1252 = '€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ' -%}
    {%- set codes = [128, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 142,
                     145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 156, 158, 159] -%}
    case
        when ({{ expr }}) ~ '[^\x01-\x7f]'
        then convert_from(
            convert_to(
                translate({{ expr }}, '{{ cp1252 }}',
                    {% for c in codes %}chr({{ c }}){% if not loop.last %} || {% endif %}{% endfor %}),
                'LATIN1'),
            'UTF8')
        else {{ expr }}
    end
{%- endmacro %}

{#- A regex matching what double-encoded text looks like: Ã or Â followed by a character
    a UTF-8 continuation byte (0x80-0xBF) turns into under Windows-1252. A lone Â/Ã is
    fine ('Santo Ângelo'). -#}
{% macro mojibake_pattern() -%}
    '[ÂÃ][\u0080-¿€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]'
{%- endmacro %}
