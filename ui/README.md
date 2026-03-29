# Desktop UI Notes

This folder contains a minimal PySide6 desktop pet prototype.

## What it does

- Creates a transparent desktop window
- Keeps the pet always on top
- Removes the normal window frame
- Plays one exported GIF animation
- Loads `manifest.named.json` automatically when available
- Lets you drag the pet with the left mouse button
- Opens a right-click menu to switch animations or quit
- Exposes pet actions as callable methods
- Includes random behavior and random left/right walking
- Includes basic mouse interaction

## Run

```powershell
venv\Scripts\python.exe ui\main.py
```

The current default pet is `all-cats-black`.
Its named animation map lives in `asset/export/all-cats-black/manifest.named.json`.

If your current virtual environment is broken, recreate it first:

```powershell
py -m venv venv
venv\Scripts\pip install -r requirements.txt
venv\Scripts\python.exe ui\main.py
```

## Key ideas

`QMainWindow`
- The desktop window container.

`Qt.FramelessWindowHint`
- Removes the normal title bar and border.

`Qt.WindowStaysOnTopHint`
- Keeps the pet visible above regular windows.

`WA_TranslucentBackground`
- Makes the background transparent so only the pet appears.

`QLabel + QMovie`
- Displays and plays the exported GIF animation.

Mouse events
- Used to implement click-and-drag movement.

Context menu
- Used to switch animations without adding visible UI controls.

## Action Methods

`PetWindow` now exposes direct action methods that you can call from your own logic:

- `pet.call_action("idle")`
- `pet.call_action("happy")`
- `pet.call_action("full")`
- `pet.call_action("sleeping")`
- `pet.call_action("chilling")`
- `pet.call_action("prone")`
- `pet.call_action("stay_box")`
- `pet.call_action("hide_in_box")`
- `pet.call_action("out_of_box")`
- `pet.call_action("cry")`
- `pet.call_action("dance")`
- `pet.call_action("tickle")`
- `pet.call_action("supprised")`
- `pet.call_action("jumping")`
- `pet.call_action("dying")`
- `pet.call_action("running")`
- `pet.call_action("running_left")`
- `pet.call_action("get_hurts")`
- `pet.call_action("attack")`
- `pet.call_action("excited")`
- `pet.walk_left()`
- `pet.walk_right()`
- `pet.eat()`
- `pet.sleep()`
- `pet.hiss()`
- `pet.jump()`
- `pet.random_idle()`
- `pet.random_emote()`
- `pet.random_walk()`
- `pet.start_random_behavior()`
- `pet.stop_random_behavior()`

You can also call actions by name:

```python
pet.call_action("walk_left")
pet.call_action("sleep")
pet.call_action("random_walk")
```

## Mouse Interaction

- Left click: trigger a reaction animation
- Left double click: jump toward the mouse side
- Long press: trigger a "petting" reaction
- Move the cursor near the pet: it reacts and turns toward the cursor
- Move the cursor very close: it follows the cursor a short distance
- Repeated fast clicks: it gets annoyed and jumps away
- Left drag: move the pet window
- Release after dragging: it plays a landing/recovery reaction
- Right click: open the action menu
