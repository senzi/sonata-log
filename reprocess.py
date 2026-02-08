import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIDI_DIR = os.path.join(BASE_DIR, 'static', 'midi')
DB_PATH = os.path.join(BASE_DIR, 'instance', 'sonata.db')
ARCHIVE_DIR = os.path.join(BASE_DIR, 'archive')
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')

def reset_and_reprocess():
    print("--- 开始重置与重跑流程 ---")

    # 1. 删除生成的 MIDI 文件
    if os.path.exists(MIDI_DIR):
        print(f"正在清空 MIDI 目录: {MIDI_DIR}")
        shutil.rmtree(MIDI_DIR)
        os.makedirs(MIDI_DIR)
    else:
        print("MIDI 目录不存在，无需删除。")
        os.makedirs(MIDI_DIR, exist_ok=True)

    # 2. 删除数据库
    if os.path.exists(DB_PATH):
        print(f"正在删除数据库: {DB_PATH}")
        try:
            os.remove(DB_PATH)
        except Exception as e:
            print(f"删除数据库失败 (可能被占用?): {e}")
    else:
        print("数据库不存在，无需删除。")

    # 3. 将 Archive 中的文件移动回 Uploads
    if os.path.exists(ARCHIVE_DIR):
        files = [f for f in os.listdir(ARCHIVE_DIR) if f.lower().endswith('.wav')]
        if not files:
            print("Archive 目录为空，没有文件需要重跑。")
        else:
            print(f"发现 {len(files)} 个待重跑文件，正在移动至 Uploads...")
            os.makedirs(UPLOADS_DIR, exist_ok=True)
            for f in files:
                src = os.path.join(ARCHIVE_DIR, f)
                dst = os.path.join(UPLOADS_DIR, f)
                try:
                    shutil.move(src, dst)
                    print(f"已移动: {f}")
                except Exception as e:
                    print(f"移动失败 {f}: {e}")
    else:
        print("Archive 目录不存在。")

    print("\n--- 重置完成 ---")
    print("请确保 app.py 正在运行 (或重启 app.py)，后台将自动开始分析 Uploads 中的文件。")

if __name__ == "__main__":
    # 简单的确认
    confirm = input("确定要删除所有数据并重新处理 Archive 中的录音吗? (y/n): ")
    if confirm.lower() == 'y':
        reset_and_reprocess()
    else:
        print("操作已取消。")
