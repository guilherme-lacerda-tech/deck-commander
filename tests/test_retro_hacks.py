"""Botões de trás (L4/R4/L5/R5 → F9/F10/F11/F12) nos emuladores e no Steam Input — docs/specs/retro_hacks.md."""
from dc import retro_hacks as R

LAYOUT = '''"controller_mappings"
{
	"group"
	{
		"id"		"7"
		"mode"		"switches"
		"inputs"
		{
			"left_bumper"
			{
				"activators"
				{
					"Full_Press"
					{
						"bindings"
						{
							"binding"		"xinput_button shoulder_left"
						}
					}
				}
			}
			"button_back_left"
			{
				"activators"
				{
					"Full_Press"
					{
						"bindings"
						{
						}
					}
				}
			}
			"button_back_right"
			{
				"activators"
				{
					"Full_Press"
					{
						"bindings"
						{
							"binding"		"key_press R, Reload"
						}
					}
				}
			}
			"button_back_left_upper"
			{
				"activators"
				{
					"Full_Press"
					{
						"bindings"
						{
						}
					}
				}
			}
			"button_back_right_upper"
			{
				"activators"
				{
					"Full_Press"
					{
						"bindings"
						{
						}
					}
				}
			}
		}
	}
}
'''


def test_retroarch():
    t = 'a = "1"\nfastforward_ratio = "0.000000"\ninput_rewind = "r"'
    r = R.cfg_retroarch(t)
    assert r.startswith('a = "1"\nfastforward_ratio = "2.000000"\n')
    for k, v in (("input_save_state", "f9"), ("input_load_state", "f10"), ("input_rewind", "f11"),
                 ("input_toggle_fast_forward", "f12"), ("input_hold_fast_forward", "nul"), ("rewind_enable", "true"), ("network_cmd_enable", "true"),
                 ("apply_cheats_after_load", "true")):
        assert f'{k} = "{v}"' in r
    assert r.count("input_rewind") == 1 and '"r"' not in r
    assert R.cfg_retroarch(r) == r  # aplicar de novo não muda nada
    assert 'fastforward_ratio = "4.000000"' in R.cfg_retroarch(t, turbo=4)
    # falha real: F13–F16 viram "XF86Tools…" no Linux e não chegam ao emulador → F9–F12, tirando as funções antigas
    c = R.cfg_retroarch('input_audio_mute = "f9"\ninput_grab_mouse_toggle = "f11"\ninput_menu_toggle = "f1"\n')
    assert 'input_audio_mute = "nul"' in c and 'input_grab_mouse_toggle = "nul"' in c and 'input_menu_toggle = "f1"' in c
    assert all(t not in R.BOTOES_DE_TRAS[b][0] for b in R.BOTOES_DE_TRAS for t in ("F13", "F14", "F15", "F16"))


def test_override_e_shader():
    o = R.override_nucleo(None, runahead=True, rewind=False, shader="crt")
    assert 'run_ahead_enabled = "true"' in o and 'rewind_enable = "false"' in o and 'run_ahead_frames = "1"' in o
    assert R.NUCLEOS["Mupen64Plus-Next"]["runahead"] is False and R.NUCLEOS["Snes9x"]["shader"] == "crt"
    assert R.preset_shader("crt") == '#reference "/app/share/libretro/shaders/shaders_slang/crt/zfast-crt.slangp"\n'


def test_duckstation_e_pcsx2():
    i = "[Hotkeys]\nFastForward = Keyboard/Tab\nScreenshot = Keyboard/F12\n\n[Main]\nX = 1\n"
    d = R.ini_duckstation(i)
    assert "ToggleFastForward = Keyboard/F12" in d and "Screenshot" not in d and "X = 1" in d and "RewindEnable = true" in d and "RewindSaveSlots = 20" in d
    assert d.index("SaveSelectedSaveState") < d.index("[Main]")  # entrou na seção certa
    assert R.ini_duckstation(d) == d
    p = R.ini_pcsx2("[Hotkeys]\nToggleTurbo = Keyboard/Tab\nHoldTurbo = Keyboard/Period\n\n[Pad]\nA = 1\n")
    assert "ToggleTurbo = Keyboard/F12" in p and "SaveStateToSlot = Keyboard/F9" in p and "[Framerate]" in p
    assert "TurboScalar = 2.000000" in p


def test_dolphin():
    h = R.hotkeys_dolphin(None)
    assert "[Hotkeys]" in h and "Device = XInput2/0/Virtual core pointer" in h
    assert "Save State/Save to Selected Slot = `F9`" in h and "Load State/Load from Selected Slot = `F10`" in h


def test_layout_steam():
    assert not R.tem_botoes_de_tras(LAYOUT)
    r = R.layout_com_botoes_de_tras(LAYOUT)
    assert R.tem_botoes_de_tras(r)
    assert '"key_press F9, Salvar estado"' in r and '"key_press F10, Carregar estado"' in r
    assert '"key_press R, Reload"' not in r  # o R4 antigo foi trocado
    assert '"xinput_button shoulder_left"' in r  # o resto ficou
    assert r.count("{") == r.count("}")
    assert R.layout_com_botoes_de_tras(r) == r
