## Cài đặt
```
sudo apt-get update
sudo apt-get install ros-noetic-navigation
sudo apt-get install ros-noetic-gmapping
sudo apt-get install ros-noetic-openslam-gmapping
sudo apt-get install ros-noetic-teleop-twist-keyboard
sudo apt-get install -y espeak portaudio19-dev python3-pyaudio
pip3 install SpeechRecognition
pip3 install gTTS
sudo apt-get install mpg321
```

## Cấp quyền thực thi cho file script
```
roscd hospital_robot
chmod +x scripts/voice_navigation.py
```

## CÁCH CHẠY
```
roslaunch hospital_robot gazebo.launch
roslaunch hospital_robot navigation.launch
```

## CÁCH THÊM ĐỊA ĐIỂM ROBOT ĐẾN
1. Chạy 2 file launch như trên
2. Mở cửa sổ Rviz, chọn nút Publish Point bên trên, di chuột vào vị trí muốn thêm, nhìn bên dưới góc trái có tọa độ. Thêm tọa độ đấy vào file Python trong thư mục scripts như mấy cái đã có sẵn.
