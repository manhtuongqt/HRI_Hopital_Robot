# Mô phỏng Robot Dịch vụ Bệnh viện (HRI) 

Hệ thống tương tác Người - Robot (HRI) tiên tiến cho robot dịch vụ trong môi trường y tế. Dự án tích hợp các mô hình ngôn ngữ lớn (LLM) với hệ điều hành Robot (ROS) để thực hiện điều hướng thông minh và hỗ trợ bệnh nhân bằng giọng nói.

---

##  Các Tính năng Nổi bật

- **Hiểu ngôn ngữ tự nhiên (NLU)**: Tích hợp **GPT-4o-mini API** để xử lý các câu hỏi phức tạp của bệnh nhân và trích xuất ý định điều hướng từ lời nói tự nhiên (không chỉ là câu lệnh đơn lẻ).

- **Luồng Speech-to-Intent**: Quy trình xử lý giọng nói thời gian thực sử dụng `SpeechRecognition` (STT) và `gTTS` (TTS), cho phép tương tác rảnh tay hoàn toàn.

- **Prompt Engineering chuyên dụng**: Hệ thống prompt được thiết kế riêng cho môi trường y tế, đảm bảo robot nhận diện đúng khoa/phòng và đưa ra phản hồi phù hợp.

- **Hỗ trợ dựa trên ngữ cảnh**: Kết nối với **SQLite backend** chứa sơ đồ bệnh viện, danh sách khoa và dữ liệu bệnh nhân để cá nhân hóa trải nghiệm dẫn đường.

- **Điều hướng tự động (Navigation)**: Tích hợp mượt mà với **ROS Navigation Stack (MoveBase)** và Gazebo để robot di chuyển chính xác trên bản đồ 2D/3D.

---

## 🏗️ Kiến trúc Hệ thống

1. **Nhận thức (Perception)**: Thu âm giọng nói → Chuyển thành văn bản (STT).

2. **Trí tuệ (Intelligence)**: Gửi văn bản tới **GPT-4o-mini** kèm prompt ngữ cảnh y tế → Trả về ý định dưới dạng JSON (Ví dụ: `{"location": "Khoa Nội", "action": "navigate"}`).

3. **Cơ sở dữ liệu**: Truy vấn **SQL Database** nếu cần thông tin cá nhân của bệnh nhân hoặc chi tiết phòng ban.

4. **Hành động (Action)**: Gửi mục tiêu (goal) tới **MoveBase** → Robot tự tìm đường trong Gazebo.

5. **Phản hồi (Feedback)**: Cập nhật trạng thái và hỏi đáp với bệnh nhân thông qua giọng nói (TTS).

---

## 📂 Cấu trúc Thư mục

- `voice_navigation.py`: Node chính xử lý toàn bộ logic HRI, LLM và điều hướng ROS.

- `init_db.py`: Script khởi tạo cơ sở dữ liệu mẫu cho bệnh viện.

- `hospital_demo.db`: File SQLite lưu trữ dữ liệu khoa phòng và bệnh nhân.

- `scripts/`: Chứa các script bổ trợ và cấu hình node.

- `worlds/` & `maps/`: Các file mô phỏng môi trường bệnh viện và bản đồ SLAM.

---

## 🚀 Hướng dẫn Cài đặt

### Yêu cầu hệ thống

- ROS Noetic (khuyên dùng Ubuntu 20.04)

- Python 3.8+

- Các thư viện Python cần thiết:
  ```bash
  pip install SpeechRecognition gTTS requests
## Các bước thực hiện
### 1.Clone repository:
git clone https://github.com/manhtuongqt/HRI_Hopital_Robot.git
cd HRI_Hopital_Robot
### 2.Khởi tạo cơ sở dữ liệu:
python3 init_db.py
### 3.Khởi chạy simulation (hãy đảm bảo bạn đã source workspace ROS):
roslaunch hospital_simulation hospital.launch
### 4.Chạy node điều khiển bằng giọng nói:
python3 voice_navigation.py
## Cấu hình
### Để sử dụng tính năng LLM, bạn cần cấu hình OpenAI API key trong file voice_navigation.py:
### voice_navigation.py 
### api_key = "YOUR_OPENAI_API_KEY"
