#!/usr/bin/env python3
"""
丰田车型图片爬取脚本
来源：Bing 图片搜索
输出：backend/data/images/{车型名}/000001.jpg ...
"""
import os, sys, time, json

# 添加路径
sys.path.insert(0, '/mnt/e/claude/1work/CRMBOT/backend')

from icrawler.builtin import BingImageCrawler

# 知识库中的 26 款丰田车型
TOYOTA_MODELS = [
    # 家用轿车
    "丰田凯美瑞", "丰田雷凌", "丰田亚洲龙", "丰田凌尚",
    "丰田铂智7", "丰田bZ3", "丰田bZ5",
    # SUV
    "丰田汉兰达", "丰田普拉多", "丰田RAV4荣放", "丰田锋兰达",
    "丰田威兰达", "丰田卡罗拉锐放", "丰田皇冠陆放", "丰田凌放HARRIER",
    "丰田威飒", "丰田铂智3X", "丰田铂智4X",
    # MPV
    "丰田赛那SIENNA", "丰田格瑞维亚",
    # 进口
    "丰田埃尔法", "丰田威尔法", "丰田皇冠SportCross",
    "丰田SUPRA", "丰田Mirai", "丰田柯斯达",
]

# 输出根目录
OUTPUT_ROOT = "/mnt/e/claude/1work/CRMBOT/backend/data/images"
IMAGES_PER_MODEL = 5

def sanitize_name(name: str) -> str:
    """清理车型名作为目录名"""
    return name.replace("丰田", "").replace("/", "-").replace(" ", "_").strip()

def download_images(model: str, out_dir: str, count: int = 5):
    """下载指定车型的图片"""
    os.makedirs(out_dir, exist_ok=True)
    
    # 用多个关键词组合提高命中率
    keywords = [
        f"{model} 官方图片",
        f"{model} 外观",
    ]
    
    total = 0
    for keyword in keywords:
        if total >= count:
            break
        remaining = count - total
        try:
            crawler = BingImageCrawler(
                storage={"root_dir": out_dir},
                downloader_threads=2,
                log_level="WARNING",
            )
            crawler.crawl(
                keyword=keyword,
                max_num=min(remaining + 2, 10),  # 多爬几张以防过滤
                file_idx_offset=total,
            )
            # 统计实际下载数
            actual = len([f for f in os.listdir(out_dir) if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))])
            total = actual
        except Exception as e:
            print(f"    ⚠️ 关键词 '{keyword}' 出错: {e}")
            time.sleep(2)
    
    return total

def main():
    print("=" * 60)
    print("丰田车型图片批量下载")
    print(f"目标: {len(TOYOTA_MODELS)} 款车型, 每款 {IMAGES_PER_MODEL} 张")
    print(f"输出: {OUTPUT_ROOT}")
    print("=" * 60)
    
    results = {}
    success = 0
    failed = []
    
    for i, model in enumerate(TOYOTA_MODELS, 1):
        dirname = sanitize_name(model)
        out_dir = os.path.join(OUTPUT_ROOT, dirname)
        
        print(f"\n[{i}/{len(TOYOTA_MODELS)}] {model} → {dirname}/")
        
        try:
            count = download_images(model, out_dir, IMAGES_PER_MODEL)
            results[model] = count
            if count > 0:
                success += 1
                print(f"    ✅ 下载 {count} 张")
            else:
                failed.append(model)
                print(f"    ❌ 0 张")
        except Exception as e:
            failed.append(model)
            results[model] = 0
            print(f"    ❌ {e}")
        
        # 礼貌间隔，避免被封
        time.sleep(1.5)
    
    # 汇总
    print("\n" + "=" * 60)
    print("下载完成!")
    print(f"  成功: {success}/{len(TOYOTA_MODELS)} 款")
    if failed:
        print(f"  失败: {', '.join(failed)}")
    
    total_imgs = sum(results.values())
    print(f"  总图片: {total_imgs} 张")
    
    # 保存结果
    with open(os.path.join(OUTPUT_ROOT, "download_report.json"), "w", encoding="utf-8") as f:
        json.dump({"results": results, "total": total_imgs, "failed": failed}, 
                  f, ensure_ascii=False, indent=2)
    
    print(f"  报告: {OUTPUT_ROOT}/download_report.json")
    
    # 打印目录结构
    print("\n目录结构:")
    for d in sorted(os.listdir(OUTPUT_ROOT)):
        dpath = os.path.join(OUTPUT_ROOT, d)
        if os.path.isdir(dpath):
            imgs = [f for f in os.listdir(dpath) if f.endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            print(f"  {d}/ ({len(imgs)} 张)")

if __name__ == "__main__":
    main()
