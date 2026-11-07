-- Fixed cases for macros/repair_mojibake.sql, taken from EDGAR v2024. Returns failures.
with cases (source, expected) as (
    values
        ('SÃ£o Paulo', 'São Paulo'),
        ('MÃ©xico', 'México'),
        ('Ã‡orum', 'Çorum'),
        ('ÃšstÃ­ nad Labem', 'Ústí nad Labem'),
        ('Freiburg im Ãœechtland', 'Freiburg im Üechtland'),
        ('Los Ã' || chr(129) || 'ngeles', 'Los Ángeles'),      -- 0x81: undefined in Windows-1252
        ('Santo Ã‚ngelo', 'Santo Ângelo'),
        ('Bia?ystok', 'Bia?ystok'),                            -- lost upstream: unchanged
        ('Kigali', 'Kigali'),
        (null, null)
)

select source, expected, {{ repair_mojibake('source') }} as got
from cases
where {{ repair_mojibake('source') }} is distinct from expected
