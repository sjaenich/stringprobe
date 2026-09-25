from core.project import ComparisonResult


class ResultComparator:
    def compare(
        self,
        recovered: set[str],
        ground_truth: set[str],
    ) -> ComparisonResult:
        tp = set()
        fp = set()
        fn = set()

        recovered_single = set()
        for (m,_) in recovered:
            recovered_single.add(m)
        print("Recovered single:", recovered_single)
        ground_truth_single = set()
        for (m,_) in ground_truth:
            ground_truth_single.add(m)
        print("Ground truth single:", ground_truth_single)

        tp_single = recovered_single & ground_truth_single

        for (m,b) in recovered:
            if m in ground_truth_single:
                if (m,b) in ground_truth:
                    tp.add((m,b))
                else:
                    fp.add((m,b))
        for (m,b) in ground_truth:
            if m not in recovered_single:
                fn.add((m,b)) 
        

        print("True Positives:", tp)
        print("False Positives:", fp)
        print("False Negatives:", fn)
    

        precision = len(tp) / (len(tp) + len(fp)) if tp or fp else 0.0
        recall = len(tp) / (len(tp) + len(fn)) if tp or fn else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )

        return ComparisonResult(precision, recall, f1, tp, fp, fn)
