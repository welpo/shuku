# shuku demo tape

####################################################
# vhs config: https://github.com/charmbracelet/vhs #
#    create the video with: vhs shuku_demo.tape    #
####################################################
Set Shell "bash"
Set FontSize 18
Set Width 1200
Set Height 600
Set FontFamily "Monolisa Script"
Set CursorBlink false
Set TypingSpeed 85ms
Output shuku_demo.mp4
Output shuku_demo.gif
# Require shuku

#################
# Set the stage #
#################
Hide
Type 'cd ~/git/shuku' Enter
Type 'poetry shell' Enter
Sleep 2s
Type 'cd ~/アニメ' Enter
Type 'mv ~/.config/shuku/shuku.toml ~/.config/shuku/shuku.toml.backup' Enter
Sleep 1s
Type 'export PS1="\[\033[0;35m\]> \[\033[0m\]"' Enter
Type 'clear' Enter
Show

####################
# Actual recording #
####################
Sleep 1s
Type 'ls'
Enter
Sleep 2.8s
Type 'shuku *mkv'
Tab
Sleep 0.3s
Enter
Sleep 27s  # shuku processes the video…
Type "ls"
Enter
Sleep 5s

###########
# Cleanup #
###########
Hide
Type 'rm *ogg' Enter
Type 'mv ~/.config/shuku/shuku.toml.backup ~/.config/shuku/shuku.toml' Enter
Show
