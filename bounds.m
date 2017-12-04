function [lb, ub] = bounds(n_y)
    %lb = -10 * ones(n_y, 1);
    %ub = 10 * ones(n_y, 1);
       
    lb = 0.35 * ones(n_y, 1);
    ub = 0.65 * ones(n_y, 1);
    
    for i = 1:floor(n_y/4)
        lb(i) = -Inf;
        lb(n_y-i+1) = -Inf;
        
        ub(i) = Inf;
        ub(n_y-i+1) = Inf;
    end
end

