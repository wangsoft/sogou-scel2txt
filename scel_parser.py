import struct
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple

@dataclass
class WordLibrary:
    word: str
    pinyin: List[str]
    rank: int = 1

def read_scel_info(file_path: str) -> Dict[str, str]:
    """读取搜狗细胞词库的元信息"""
    info = {}
    with open(file_path, 'rb') as f:
        # 移动到词条数量位置 (0x124)
        f.seek(0x124)
        count_word = struct.unpack('<I', f.read(4))[0]
        info['CountWord'] = str(count_word)
        
        # 读取各个元数据字段
        info['Name'] = _read_scel_field_text(f, 0x130)
        info['Type'] = _read_scel_field_text(f, 0x338)
        info['Info'] = _read_scel_field_text(f, 0x540, 1024)
        info['Sample'] = _read_scel_field_text(f, 0xD40, 1024)
    
    return info

def _read_scel_field_text(f, seek_pos: int, length: int = 64) -> str:
    """从指定位置读取Unicode文本"""
    current_pos = f.tell()
    f.seek(seek_pos)
    
    # 读取并解码文本 (UTF-16LE)
    data = f.read(length)
    try:
        text = data.decode('utf-16-le', errors='ignore')
    except UnicodeDecodeError:
        # 尝试GBK解码作为备选
        text = data.decode('gbk', errors='ignore')
    
    # 截取到第一个空字符
    null_pos = text.find('\x00')
    if null_pos >= 0:
        text = text[:null_pos]
    
    f.seek(current_pos)
    return text.strip()

def parse_scel(file_path: str) -> List[WordLibrary]:
    """解析搜狗细胞词库(.scel)文件"""
    word_libraries = []
    py_dict = {}
    
    with open(file_path, 'rb') as f:
        # 读取词库基本信息
        f.seek(0x120)
        dict_len = struct.unpack('<I', f.read(4))[0]  # 词条数量
        
        # 定位到拼音表起始位置 (0x1540)
        f.seek(0x1540)
        py_dict_len = struct.unpack('<I', f.read(4))[0]  # 拼音表长度
        
        # 解析拼音表
        for _ in range(py_dict_len):
            idx = struct.unpack('<H', f.read(2))[0]
            size = struct.unpack('<H', f.read(2))[0]
            py_data = f.read(size)
            
            try:
                # 尝试UTF-16LE解码
                py_str = py_data.decode('utf-16-le')
            except UnicodeDecodeError:
                # 尝试GBK解码作为备选
                py_str = py_data.decode('gbk', errors='ignore')
            
            # 移除可能的空字符
            py_str = py_str.replace('\x00', '').strip()
            py_dict[idx] = py_str
        
        # 解析词条
        for _ in range(dict_len):
            try:
                words = _parse_pinyin_word(f, py_dict)
                word_libraries.extend(words)
            except Exception as e:
                print(f"解析词条时出错: {str(e)}")
                # 尝试恢复位置到下一个词条
                if f.tell() % 2 != 0:
                    f.read(1)  # 对齐到偶数字节
    
    return word_libraries

def _parse_pinyin_word(f, py_dict: Dict[int, str]) -> List[WordLibrary]:
    """解析单个拼音词条组"""
    # 读取同音词数量和拼音索引数量
    header = f.read(4)
    if len(header) < 4:
        return []
    
    same_py_count = header[0] + (header[1] << 8)
    py_index_count = header[2] + (header[3] << 8)
    
    # 读取拼音索引
    py_data = f.read(py_index_count)
    word_py = []
    
    # 每2个字节组成一个拼音索引
    for i in range(0, len(py_data), 2):
        if i + 1 >= len(py_data):
            break
            
        # 小端序解析拼音索引
        idx = py_data[i] + (py_data[i + 1] << 8)
        if idx in py_dict:
            word_py.append(py_dict[idx])
        else:
            # 生成备用拼音 (a, b, c, ...)
            word_py.append(chr(97 + (idx % 26)))
    
    # 解析同音词
    words = []
    for _ in range(same_py_count):
        # 读取词长
        len_data = f.read(2)
        if len(len_data) < 2:
            break
            
        word_len = len_data[0] + (len_data[1] << 8)
        
        # 读取词语
        word_data = f.read(word_len)
        try:
            word = word_data.decode('utf-16-le')
        except UnicodeDecodeError:
            word = word_data.decode('gbk', errors='ignore')
        
        # 移除空字符
        word = word.replace('\x00', '')
        
        # 跳过未知字段 (2 + 4 + 6 = 12字节)
        f.read(12)
        
        words.append(WordLibrary(
            word=word,
            pinyin=word_py.copy(),
            rank=1
        ))
    
    return words

def save_to_txt(word_libraries: List[WordLibrary], output_path: str):
    """将词库保存为文本文件"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for wl in word_libraries:
            # 格式: 词语 + 拼音 (空格分隔)
            py_str = ' '.join(wl.pinyin)
            # f.write(f"{wl.word}\t{py_str}\n")
            f.write(f"{wl.word}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python scel_parser.py <输入.scel> [输出.txt]")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else "output.txt"
    
    if not os.path.exists(input_path):
        print(f"错误: 文件不存在 {input_path}")
        sys.exit(1)
    
    try:
        # 显示词库信息
        print("解析词库信息...")
        info = read_scel_info(input_path)
        for k, v in info.items():
            print(f"{k}: {v}")
        
        # 解析词库内容
        print("解析词条内容...")
        word_libraries = parse_scel(input_path)
        print(f"成功解析 {len(word_libraries)} 个词条")
        
        # 保存结果
        save_to_txt(word_libraries, output_path)
        print(f"结果已保存到: {output_path}")
        
    except Exception as e:
        print(f"解析失败: {str(e)}")
        import traceback
        traceback.print_exc()