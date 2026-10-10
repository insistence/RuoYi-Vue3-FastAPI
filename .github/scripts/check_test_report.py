import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def check_report(path: Path, *, allow_skips: bool = False) -> tuple[int, int]:
    """
    验证测试确实执行，专用验收任务不允许缺少依赖而全部跳过。

    :param path: pytest JUnit 报告路径
    :param allow_skips: 是否允许普通跨平台回归中的预期跳过
    :return: 实际执行及跳过的测试数量
    """
    root = ET.parse(path).getroot()
    cases = root.findall('.//testcase')
    skipped = sum(case.find('skipped') is not None for case in cases)
    executed = len(cases) - skipped
    failures = sum(case.find('failure') is not None or case.find('error') is not None for case in cases)
    if executed == 0 or failures or (skipped and not allow_skips):
        raise ValueError(f'{path}: 执行 {executed}，跳过 {skipped}，失败 {failures}')
    return executed, skipped


def main() -> None:
    """
    检查报告并将执行数量写入 CI 摘要。

    :return: None
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('report', type=Path)
    parser.add_argument('--allow-skips', action='store_true')
    args = parser.parse_args()
    executed, skipped = check_report(args.report, allow_skips=args.allow_skips)
    print(f'{args.report}: executed={executed}, skipped={skipped}')


if __name__ == '__main__':
    main()
