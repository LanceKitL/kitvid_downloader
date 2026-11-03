# Running the App on a Mac

## First time only

1. Press **Command (⌘) + Space**, type **Terminal**, press **Enter**.

2. Paste this and press **Enter**:
   ```
   brew --version
   ```
   If it shows a version number, go to step 4. If it says `command not found`, do step 3.

3. Install Homebrew. Paste this and press **Enter**:
   ```
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
   Type your Mac password when asked (nothing shows while you type, that's normal). Wait until it finishes.

4. Type `cd ` (with a space after it), then drag the app's folder into the Terminal window and press **Enter**.

5. Paste this and press **Enter**:
   ```
   bash start.sh
   ```

6. Wait 5–15 minutes. The app opens when setup is done.

## Every time after that

1. Open **Terminal**.
2. Type `cd `, drag the app's folder into the window, press **Enter**.
3. Run:
   ```
   bash start.sh
   ```

## If something goes wrong

- **Stuck or failed:** press **Control + C**, check your internet, and run `bash start.sh` again.
- **Still failing:** take a screenshot of the Terminal window and send it lance.gomos.it@gmail.com