# Package requirements

System packages:
* `python-pygame` (required beyond `pip` install due to SDL shared library dependencies)
* `xorg-xvfb-server`
* `imagemagick`
* `libatlas-base-dev` on RaspberryPi (otherwise `numpy` fails shared library dependency)

# X windows

X programs can be displayed using `xvfb_client.py`:

```
$ ./xvfb_client.py 192.168.1.112 --x_dim 100x100 --x_display 1
```

and then:

```
$ DISPLAY=:1 feh pikachu.jpg
```

The virtual display is hosted by `Xvfb`. The client periodically samples the virtual frame buffer,
resizes it if necessary, and sends it to the target display. The frame buffer is presented as a XWD
file. The client internally converts it to a bitmap with `convert` by ImageMagick. It's important
that `-nocursor` is passed to `Xvfb`, since otherwise there can be artifacts.

If the X program accepts stdin (for example, `feh` accepts arrow keys for zoom),  the program can be
interacted with in the terminal. X programs like shells can also be interacted with by sending X
mouse/keyboard events:

```
$ DISPLAY=:1 urxvt -b 0 -fn "xft:Anonymous Pro:pixelsize=10" -e bash
```

and then:

```
$ DISPLAY=:1 xdotool type 'watch -t date'
$ DISPLAY=:1 xdotool key Return
```

Alternatively, to just watch characters appear in the shell input buffer, do `bash --rcfile <(echo
export PS1='')`.

# Color

Colors are gamma-corrected (raised to power 2.3) before display.

Examined some Python color libraries:
* `palette` hasn't changed in ~10 years and does not support python 3
* `colour` is most promising, but it does not natively support 8-bit scaled colors
* `python-colormath` unfortunately has a separate type for each color representation
