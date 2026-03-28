# Desktop UI Notes

This folder contains a minimal PySide6 desktop pet prototype.

## What it does

- Creates a transparent desktop window
- Keeps the pet always on top
- Removes the normal window frame
- Plays one exported GIF animation
- Lets you drag the pet with the left mouse button
- Opens a right-click menu to switch animations or quit
- Exposes pet actions as callable methods
- Includes random behavior and random left/right walking

## Run

```powershell
venv\Scripts\python.exe ui\main.py
```

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

- `pet.sit()`
- `pet.idle_sit()`
- `pet.idle_stand()`
- `pet.idle_lie()`
- `pet.walk_left()`
- `pet.walk_right()`
- `pet.run_left()`
- `pet.run_right()`
- `pet.eat()`
- `pet.sleep()`
- `pet.hiss()`
- `pet.jump()`
- `pet.yawn()`
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
